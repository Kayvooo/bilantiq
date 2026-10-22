import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.ai.routes import router as ai_router
from app.auftraege.routes import router as auftraege_router
from app.auth.routes import router as auth_router
from app.buchhaltungseinstellungen.routes import router as buchhaltungseinstellungen_router
from app.config import settings
from app.core.audit_log import AuditLogAppendOnlyError
from app.core.storage_check import SpeicherFehler, pruefe_speicher
from app.core.runtime_security import pruefe_datenbankrolle
from app.core.zugriffslog import installiere_zugriffslog_maskierung
from app.db import Base, IS_POSTGRES, engine
from app.einnahmen.routes import router as einnahmen_router
from app.invoices.routes import router as invoices_router
from app.mahnwesen.routes import router as mahnwesen_router
from app.payroll.routes import router as payroll_router
from app.produkte.routes import router as produkte_router
from app.quotes.routes import router as quotes_router
from app.bank.routes import router as bank_router
from app.erste_schritte.routes import router as erste_schritte_router
from app.receipts.routes import router as receipts_router
from app.reports.routes import router as reports_router
from app.security.routes import router as security_router
from app.altrechnungen.models import Altrechnung, AltrechnungZahlung  # noqa: F401 (registers models on Base)
from app.altrechnungen.routes import kontakt_router as kontakt_historie_router, router as altrechnungen_router
from app.nummernkreis.routes import router as nummernkreis_router
from app.stammdaten.routes import router as stammdaten_router
from app.umzug.routes import router as umzug_router
from app.suche.routes import router as suche_router
from app.wiederkehrend.ausgaben_routes import router as wiederkehrend_ausgaben_router
from app.wiederkehrend.routes import router as wiederkehrend_router
from app.kassenbuch.routes import router as kassenbuch_router
from app.anlagen.routes import router as anlagen_router


logger = logging.getLogger(__name__)

if settings.database_url.startswith("postgres") and "*" in settings.trusted_hosts:
    # Postgres heisst praktisch "echte Umgebung". Fehlt TRUSTED_HOSTS_RAW (oder APP_ENV), ist der Host-Header-Schutz aus.
    logger.warning(
        "TRUSTED_HOSTS_RAW erlaubt jeden Host (Standard '*') bei Postgres-Datenbank: In Produktion/Staging "
        "APP_ENV=production|staging und TRUSTED_HOSTS_RAW=<echte Domain> setzen."
    )

# uvicorn richtet sein Logging vor dem Import der App ein; der Filter bleibt danach am Logger haengen.
installiere_zugriffslog_maskierung()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    pruefe_datenbankrolle(engine, settings.app_env)
    installiere_zugriffslog_maskierung()  # idempotent; falls ein Logging-Reset dazwischenkam
    # Dateispeicher (STORAGE_DIR) pruefen, bevor Anfragen angenommen werden: lieber jetzt mit klarer Meldung stoppen
    # als beim ersten Beleg-Upload mit einem 500er. Im Docker-Image laeuft dieselbe Pruefung zusaetzlich vorab als
    # Kommando (python -m app.core.storage_check) und beendet sich dort ohne Stacktrace.
    try:
        speicher = pruefe_speicher()
    except SpeicherFehler as exc:
        logger.critical("%s", exc)
        raise
    for warnung in speicher.warnungen:
        logger.warning("Speicher: %s", warnung)
    if not settings.email_aktiv:
        logger.warning(
            "E-Mail ist nicht eingerichtet (SMTP_HOST/SMTP_USER/SMTP_PASSWORD/Absenderadresse): Versand von Rechnungen "
            "und 'Passwort vergessen' sind abgeschaltet. Siehe docs/self-hosting.md."
        )
    # Postgres schema changes go through Alembic (backend/migrations) so RLS policies
    # stay in the migration history. SQLite has no migration story here — it exists only
    # for local dev/tests, so we create tables directly on startup.
    if not IS_POSTGRES:
        Base.metadata.create_all(bind=engine)
    yield


_docs_pfade = {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"} if settings.api_docs_aktiv else {
    "docs_url": None, "redoc_url": None, "openapi_url": None,
}
app = FastAPI(title="Bilantiq API", version="0.1.0", lifespan=lifespan, **_docs_pfade)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Host-Header-Schutz: verwirft Anfragen mit gefaelschtem Host-Header. Default "*"
# (lokale Entwicklung/LAN/Tests); Produktion setzt TRUSTED_HOSTS auf die echte Domain.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

# Interaktive Swagger-/ReDoc-UI braucht Skripte/Styles und wird von der strikten
# API-CSP ausgenommen; die reinen JSON-Antworten bekommen die strengste CSP.
_DOCS_PFADE = ("/docs", "/redoc")


def _setze_security_header(request: Request, response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Finanz-/Sicherheitsantworten duerfen nicht in Browser-/Proxy-Caches persistieren.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    # HSTS nur ueber HTTPS senden (hinter dem Reverse-Proxy via X-Forwarded-Proto),
    # nie auf localhost-HTTP -- sonst pinnt der Browser localhost dauerhaft auf HTTPS.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if not request.url.path.startswith(_DOCS_PFADE):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    _setze_security_header(request, response)
    return response


@app.exception_handler(Exception)
async def unbehandelter_fehler(request: Request, _exc: Exception) -> JSONResponse:
    """500 bei unbehandelten Ausnahmen. Starlettes ServerErrorMiddleware sitzt *ausserhalb* aller Middleware
    (auch der oben), die Antwort liefe sonst ohne Security-Header. Der Handler setzt sie selbst und gibt bewusst
    keine Details preis; ServerErrorMiddleware reicht die Ausnahme danach weiter, sodass uvicorn den Traceback
    wie bisher ins Log schreibt."""
    antwort = JSONResponse(status_code=500, content={"detail": "Interner Serverfehler."})
    _setze_security_header(request, antwort)
    return antwort

app.include_router(auth_router)
app.include_router(buchhaltungseinstellungen_router)
app.include_router(einnahmen_router)
app.include_router(invoices_router)
app.include_router(mahnwesen_router)
app.include_router(payroll_router)
app.include_router(produkte_router)
app.include_router(quotes_router)
app.include_router(receipts_router)
app.include_router(reports_router)
app.include_router(wiederkehrend_router)
app.include_router(wiederkehrend_ausgaben_router)
app.include_router(kassenbuch_router)
app.include_router(anlagen_router)
app.include_router(ai_router)
app.include_router(security_router)
app.include_router(auftraege_router)
app.include_router(bank_router)
app.include_router(erste_schritte_router)
app.include_router(stammdaten_router)
app.include_router(suche_router)
app.include_router(altrechnungen_router)
app.include_router(nummernkreis_router)
app.include_router(umzug_router)
app.include_router(kontakt_historie_router)


@app.exception_handler(AuditLogAppendOnlyError)
def audit_log_append_only_handler(_request: Request, exc: AuditLogAppendOnlyError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Bereitschaftspruefung fuer Monitoring: Datenbank erreichbar?

    Liefert absichtlich nur "ok"/"unavailable" -- keine Fehlertexte, Hostnamen, Versionen oder
    Mandantendaten, damit der Endpunkt oeffentlich abfragbar bleiben kann. Die Ursache steht im Log.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Readiness-Check fehlgeschlagen: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
