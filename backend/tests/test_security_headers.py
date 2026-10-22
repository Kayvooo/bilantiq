import subprocess

from fastapi.testclient import TestClient


def test_standard_security_header_auf_api_antwort(client: TestClient):
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "Permissions-Policy" in resp.headers
    assert resp.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def test_hsts_nur_ueber_https(client: TestClient):
    ohne_https = client.get("/health")
    assert "Strict-Transport-Security" not in ohne_https.headers

    mit_https = client.get("/health", headers={"x-forwarded-proto": "https"})
    assert "Strict-Transport-Security" in mit_https.headers


def test_docs_ui_ist_von_strikter_csp_ausgenommen(client: TestClient):
    resp = client.get("/docs")
    assert resp.status_code == 200
    # Swagger-UI wuerde mit default-src 'none' brechen -> keine strikte CSP hier.
    assert "Content-Security-Policy" not in resp.headers
    # Die uebrigen Header gelten trotzdem.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_fremder_host_wird_bei_konfigurierter_allowlist_abgelehnt(client: TestClient):
    # Default ist "*" (alles erlaubt). Mit einer echten Allowlist muss ein fremder
    # Host abgelehnt werden -- TrustedHostMiddleware wird beim App-Import gebunden,
    # daher hier ueber eine frische App-Instanz mit gepatchtem Setting geprueft.
    from fastapi import FastAPI
    from fastapi.middleware.trustedhost import TrustedHostMiddleware

    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["bilantiq.de"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    lokaler_client = TestClient(app)
    erlaubt = lokaler_client.get("/health", headers={"host": "bilantiq.de"})
    assert erlaubt.status_code == 200
    abgelehnt = lokaler_client.get("/health", headers={"host": "boese.example"})
    assert abgelehnt.status_code == 400


def test_security_header_auch_auf_fehlerantworten(client: TestClient):
    """401/404/422 kommen aus Exception-Handlern unterhalb der Header-Middleware und muessen die Header trotzdem tragen."""
    antworten = {
        "404": client.get("/gibt-es-nicht"),
        "401": client.get("/auth/me"),
        "422": client.post("/auth/login", json={"email": "kein-email"}),
        "405": client.delete("/health"),
    }
    for name, resp in antworten.items():
        assert resp.status_code == int(name), name
        assert resp.headers["X-Content-Type-Options"] == "nosniff", name
        assert resp.headers["X-Frame-Options"] == "DENY", name
        assert resp.headers["Cache-Control"] == "no-store", name
        assert resp.headers["Content-Security-Policy"].startswith("default-src 'none'"), name


def test_antworten_verraten_keine_serverdetails_im_body(client: TestClient):
    fehler = client.get("/auth/me")
    assert "Traceback" not in fehler.text and "File \"" not in fehler.text
    assert "x-powered-by" not in {k.lower() for k in fehler.headers}


# ---------------------------------------------------------------------------
# Die ECHTE App mit Produktionseinstellungen (frischer Interpreter, weil Middleware und Docs-Routen beim Import gebunden werden)

_PRODUKTION = r"""
import json, os
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app, base_url="https://api.bilantiq.de")
def kopf(r, *namen): return {n: r.headers.get(n) for n in namen}

ergebnis = {}
ergebnis["host_ok"] = c.get("/health", headers={"host": "api.bilantiq.de"}).status_code
ergebnis["host_fremd"] = c.get("/health", headers={"host": "boese.example"}).status_code
ergebnis["host_fremd_hat_header"] = c.get("/health", headers={"host": "boese.example"}).headers.get("x-content-type-options")
ergebnis["docs"] = [c.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")]

pre = c.options("/invoices", headers={"host": "api.bilantiq.de", "origin": "https://bilantiq.de",
        "access-control-request-method": "GET", "access-control-request-headers": "authorization"})
ergebnis["preflight_ok"] = [pre.status_code, pre.headers.get("access-control-allow-origin"), pre.headers.get("access-control-allow-credentials")]
fremd = c.options("/invoices", headers={"host": "api.bilantiq.de", "origin": "https://evil.example",
        "access-control-request-method": "GET", "access-control-request-headers": "authorization"})
ergebnis["preflight_fremd"] = [fremd.status_code, fremd.headers.get("access-control-allow-origin")]
einfach = c.get("/health", headers={"host": "api.bilantiq.de", "origin": "https://evil.example"})
ergebnis["get_fremd_acao"] = einfach.headers.get("access-control-allow-origin")
eigen = c.get("/health", headers={"host": "api.bilantiq.de", "origin": "https://bilantiq.de"})
ergebnis["get_eigen_acao"] = eigen.headers.get("access-control-allow-origin")
ergebnis["hsts"] = eigen.headers.get("strict-transport-security")
print("ERGEBNIS=" + json.dumps(ergebnis))
"""


def _starte_mit(umgebung: dict[str, str], code: str) -> subprocess.CompletedProcess:
    import os
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k not in {"API_DOCS_AKTIV", "TRUSTED_HOSTS_RAW", "CORS_ALLOWED_ORIGINS_RAW"}}
    env.update(umgebung)
    return subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True, timeout=120)


def test_echte_app_mit_produktionseinstellungen_host_cors_docs():
    import json

    ergebnis = _starte_mit(
        {"TRUSTED_HOSTS_RAW": "api.bilantiq.de", "CORS_ALLOWED_ORIGINS_RAW": "https://bilantiq.de,https://www.bilantiq.de"},
        _PRODUKTION,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr[-2000:]
    daten = json.loads(next(z for z in ergebnis.stdout.splitlines() if z.startswith("ERGEBNIS=")).removeprefix("ERGEBNIS="))

    assert daten["host_ok"] == 200
    assert daten["host_fremd"] == 400  # gefaelschter Host-Header (TrustedHostMiddleware)
    assert daten["host_fremd_hat_header"] == "nosniff"  # auch die Ablehnung traegt die Security-Header
    assert daten["docs"] == [404, 404, 404]  # Standard in Produktion: keine API-Doku
    assert daten["preflight_ok"] == [200, "https://bilantiq.de", "true"]
    assert daten["preflight_fremd"][1] is None and daten["preflight_fremd"][0] == 400
    assert daten["get_fremd_acao"] is None  # fremde Origin bekommt keinen CORS-Freibrief
    assert daten["get_eigen_acao"] == "https://bilantiq.de"
    assert daten["hsts"] and "max-age=63072000" in daten["hsts"]


def test_cors_platzhalter_wird_beim_start_abgelehnt():
    ergebnis = _starte_mit({"CORS_ALLOWED_ORIGINS_RAW": "*"}, "from app.main import app")
    assert ergebnis.returncode != 0
    assert "CORS_ALLOWED_ORIGINS_RAW darf kein '*'" in ergebnis.stderr


def test_security_header_auch_auf_500er_antworten():
    """Unbehandelte Ausnahmen laufen ueber ServerErrorMiddleware ausserhalb der Header-Middleware."""
    from app.main import app

    @app.get("/__test_boom")
    def boom() -> None:
        raise RuntimeError("geheimes-detail-xyz")

    try:
        antwort = TestClient(app, raise_server_exceptions=False).get("/__test_boom", headers={"x-forwarded-proto": "https"})
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/__test_boom"]
    assert antwort.status_code == 500
    assert antwort.json() == {"detail": "Interner Serverfehler."}
    assert "geheimes-detail-xyz" not in antwort.text
    assert antwort.headers["X-Content-Type-Options"] == "nosniff"
    assert antwort.headers["X-Frame-Options"] == "DENY"
    assert antwort.headers["Referrer-Policy"] == "no-referrer"
    assert antwort.headers["Cache-Control"] == "no-store"
    assert antwort.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    assert "Strict-Transport-Security" in antwort.headers


def test_produktion_ohne_trusted_hosts_startet_nicht():
    for env in ("production", "staging"):
        ohne = _starte_mit({"APP_ENV": env}, "from app.main import app")
        assert ohne.returncode != 0, env
        assert "TRUSTED_HOSTS_RAW" in ohne.stderr
        stern = _starte_mit({"APP_ENV": env, "TRUSTED_HOSTS_RAW": "api.bilantiq.de,*"}, "from app.main import app")
        assert stern.returncode != 0 and "TRUSTED_HOSTS_RAW" in stern.stderr
        leer = _starte_mit({"APP_ENV": env, "TRUSTED_HOSTS_RAW": " , "}, "from app.main import app")
        assert leer.returncode != 0


def test_produktion_mit_echter_domain_und_entwicklung_ohne_angabe_starten():
    ok = _starte_mit(
        {"APP_ENV": "production", "TRUSTED_HOSTS_RAW": "api.bilantiq.de", "CORS_ALLOWED_ORIGINS_RAW": "https://bilantiq.de"},
        "from app.main import app",
    )
    assert ok.returncode == 0, ok.stderr[-2000:]
    entwicklung = _starte_mit({}, "from app.main import app")  # Standard development, Host '*' erlaubt (lokal/Tests)
    assert entwicklung.returncode == 0, entwicklung.stderr[-2000:]
    unbekannt = _starte_mit({"APP_ENV": "prod"}, "from app.main import app")
    assert unbekannt.returncode != 0 and "APP_ENV" in unbekannt.stderr


def test_postgres_ohne_trusted_hosts_warnt_auch_ohne_app_env():
    ergebnis = _starte_mit({"DATABASE_URL": "postgresql+psycopg://x:y@127.0.0.1:1/z"}, "from app.main import app")
    if ergebnis.returncode != 0 and "psycopg" in ergebnis.stderr.lower() and "No module" in ergebnis.stderr:
        import pytest
        pytest.skip("Postgres-Treiber nicht installiert")
    assert ergebnis.returncode == 0, ergebnis.stderr[-2000:]
    assert "TRUSTED_HOSTS_RAW erlaubt jeden Host" in ergebnis.stderr
