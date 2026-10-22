import json
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import bruteforce, mfa_service, passwort_reset
from app.auth.dependencies import ist_owner, require_full_auth, require_owner, require_pre_mfa
from app.auth.models import AuthSession, Briefpapier, Einladung, Mandant, Mitgliedschaft, PasswortResetToken, User
from app.auth.security_service import create_full_session, invalidate_security_context
from app.auth.schemas import (
    BriefpapierResponse,
    EinladungCreate,
    EinladungResponse,
    KontoLoeschenRequest,
    LoginRequest,
    MandantResponse,
    MandantUpdate,
    MeResponse,
    MfaAktiviertResponse,
    MfaSetupResponse,
    MfaVerifyRequest,
    MitgliedCreate,
    MitgliedCreateResponse,
    MitgliedResponse,
    PasswortAendernRequest,
    PasswortVergessenResponse,
    PreAuthResponse,
    RechnungsvorlageVorschauRequest,
    RegisterRequest,
    TokenResponse,
    WiederherstellungscodeLoginRequest,
)
from app.auth.datenexport import erstelle_datenexport
from app.config import settings
from app.core.audit_log import record as record_audit
from app.core import branding_storage, letterhead_storage, ratelimit
from app.core.bild_pruefung import UngueltigesBild, pruefe_bild
from app.core.sperren import sperre_einladung, sperre_mandant
from app.core.crypto import decrypt_field, encrypt_field, lookup_hash
from app.core.document_pdf import DocumentPosition, render_document_pdf
from app.core.rls import get_scoped_or_404
from app.core.security import (
    create_token,
    generate_mfa_secret,
    hash_password,
    password_needs_rehash,
    mfa_provisioning_uri,
    verify_password,
)
from app.core.rls_lookup import mandant_aus_einladung, mandant_des_nutzers
from app.db import get_db, set_rls_mandant

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "E-Mail oder Passwort ist falsch."

# Grenzen pro Client-IP (Gleitfenster, siehe app/core/ratelimit.py). Konto-bezogene Sperren (Passwort, MFA-Code)
# liegen zusaetzlich in der Datenbank (app/auth/bruteforce.py).
LOGIN_PRO_IP = (30, 300)        # 30 Anmeldeversuche je 5 Minuten (grosszuegig: Buero-NAT, gemeinsame Mobilfunk-IPs)
REGISTRIERUNG_PRO_IP = (10, 3600)  # 10 Registrierungsversuche je Stunde (inkl. Einladungscode-Raten)
MFA_CODE_PRO_IP = (60, 300)

# Felder von PATCH /auth/mandant, die auch Mitglieder (nicht nur der Owner) aendern duerfen: reine Darstellung der PDFs.
DESIGN_FELDER_FUER_MITGLIEDER = frozenset({
    "rechnungsvorlage", "akzentfarbe", "fusszeile_text", "design_variante", "logo_groesse", "briefpapier_id", "sprache",
    "zeige_absenderzeile", "zeige_kundennummer", "zeige_kontaktperson", "zeige_artikelnummer", "zeige_positionsbeschreibung",
    "zeige_ust_pro_position", "zeige_girocode", "zeige_fusszeile", "zeige_seitenzahlen", "zeige_falz_lochmarken",
})

_dummy_hash: str | None = None


def _dummy_passwort_pruefen(passwort: str) -> None:
    """Gleicht die Antwortzeit an, wenn kein Konto existiert/gesperrt/geloescht ist: sonst verraet die Zeit (kein
    Argon2-Durchlauf = Antwort in Millisekunden), ob die E-Mail-Adresse registriert ist."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("bilantiq-dummy-passwort")
    verify_password(passwort, _dummy_hash)


def _find_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email_lookup_hash == lookup_hash(email)).first()


def _aware_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on round-trip even for DateTime(timezone=True) columns;
    Postgres does not. Normalise so lockout comparisons work on both."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _ohne_mfa_anmelden(db: Session, request: Request, user: User, mandant_id: str) -> PreAuthResponse:
    """MFA ist optional: Wer sie nicht eingerichtet hat, bekommt direkt eine volle Sitzung. Das Frontend weist
    dringend auf die Einrichtung hin. Das pre_mfa-Token erlaubt weiterhin nur /mfa/setup und /mfa/verify."""
    _, access_token = create_full_session(
        db, user=user, mandant_id=mandant_id, user_agent=request.headers.get("user-agent"),
    )
    record_audit(db, aktion="sitzung_erstellt", mandant_id=mandant_id, user_id=user.id, kontext="ohne_mfa")
    db.commit()
    pre_auth_token = create_token(user_id=user.id, scope="pre_mfa", mandant_id=mandant_id, minutes=15, security_version=user.security_version)
    return PreAuthResponse(status="mfa_optional", pre_auth_token=pre_auth_token, access_token=access_token)


def _pruefe_registrierung_erlaubt(db: Session, payload: RegisterRequest) -> None:
    """Setzt REGISTRATION_MODE durch (siehe app/config.py und docs/self-hosting.md).

    first_account: Eine neue Firma darf nur anlegen, wer das allererste Konto der Instanz erstellt. Als "vorhanden"
    zaehlt jede Zeile in ``users``, auch anonymisierte/geloeschte Konten: Ein gelöschtes Konto öffnet die Registrierung
    nicht wieder. Grenze: Zwei exakt gleichzeitige Erstregistrierungen auf einer frischen Instanz koennten beide
    durchkommen (keine Sperre); das betrifft nur das Zeitfenster vor dem ersten Konto.
    """
    modus = settings.registration_mode
    if modus == "open":
        return
    if modus == "closed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Auf dieser Instanz ist keine Selbstregistrierung möglich. Konten legt der Inhaber unter Benutzer an.",
        )
    if payload.einladungscode:
        return  # Beitritt zu einer bestehenden Firma: der Einladungscode kommt vom Inhaber und wird unten geprueft.
    if db.query(User.id).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Auf dieser Instanz ist die Registrierung geschlossen: Das erste Konto existiert bereits. "
                "Neue Personen treten mit einem Einladungscode des Inhabers bei."
            ),
        )


@router.post("/register", response_model=PreAuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> PreAuthResponse:
    ratelimit.begrenze_ip(request, "register", limit=REGISTRIERUNG_PRO_IP[0], fenster_sekunden=REGISTRIERUNG_PRO_IP[1])
    _pruefe_registrierung_erlaubt(db, payload)
    if _find_user_by_email(db, payload.email) is not None:
        # Same generic error as a wrong login: does not confirm the email is taken.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Registrierung nicht moeglich.")

    einladung: Einladung | None = None
    if payload.einladungscode:
        jetzt = datetime.now(timezone.utc)
        einlade_mandant = mandant_aus_einladung(db, payload.einladungscode)
        if einlade_mandant is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Einladungscode ist ungueltig oder abgelaufen.")
        set_rls_mandant(db, einlade_mandant)
        einladung = sperre_einladung(db, payload.einladungscode)
        if (
            einladung is None or einladung.widerrufen or einladung.eingeloest_am is not None
            or _aware_utc(einladung.ablauf_am) < jetzt
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Einladungscode ist ungueltig oder abgelaufen.")
        mandant = sperre_mandant(db, einladung.mandant_id)
        if mandant is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Einladungscode ist ungueltig oder abgelaufen.")
    elif not payload.firmenname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Firmenname ist erforderlich.")

    user = User(
        email_encrypted=encrypt_field(payload.email),
        email_lookup_hash=lookup_hash(payload.email),
        passwort_hash=hash_password(payload.password),
    )
    db.add(user)

    if einladung is not None:
        mandant_id = einladung.mandant_id
        rolle = einladung.rolle
        einladung.eingeloest_am = datetime.now(timezone.utc)
    else:
        mandant = Mandant(id=str(uuid.uuid4()), firmenname=payload.firmenname)
        set_rls_mandant(db, mandant.id)  # vor dem Einfügen: die RLS-Regel prüft die neue Zeile
        db.add(mandant)
        db.flush()
        mandant_id = mandant.id
        rolle = "owner"

    db.flush()
    mitgliedschaft = Mitgliedschaft(user_id=user.id, mandant_id=mandant_id, rolle=rolle)
    db.add(mitgliedschaft)

    record_audit(db, aktion="registrierung", mandant_id=mandant_id, user_id=user.id)
    db.commit()

    return _ohne_mfa_anmelden(db, request, user, mandant_id)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(payload: dict = Depends(require_pre_mfa), db: Session = Depends(get_db)) -> MfaSetupResponse:
    user = db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden.")
    if user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist bereits eingerichtet.")

    # Idempotent solange MFA nicht aktiv ist: ein zweiter Aufruf (React StrictMode
    # ruft Effekte im Dev-Modus doppelt auf, ebenso ein Seiten-Reload oder ein
    # zweiter Tab) darf nicht stillschweigend einen neuen Secret erzeugen und damit
    # den bereits gescannten QR-Code ungueltig machen -- sonst wird jeder korrekte
    # Code abgelehnt, ohne dass die Nutzerin einen Fehler in ihrem Verhalten sieht.
    if user.mfa_secret_encrypted is not None:
        secret = decrypt_field(user.mfa_secret_encrypted)
    else:
        secret = generate_mfa_secret()
        user.mfa_secret_encrypted = encrypt_field(secret)
        user.mfa_letzter_zeitschritt = None  # neues Secret, neuer Replay-Zaehler
        db.commit()

    email = decrypt_field(user.email_encrypted)
    return MfaSetupResponse(secret=secret, provisioning_uri=mfa_provisioning_uri(secret=secret, email=email))


@router.post("/mfa/verify", response_model=MfaAktiviertResponse)
def mfa_verify(
    payload: MfaVerifyRequest,
    request: Request,
    token_payload: dict = Depends(require_pre_mfa),
    db: Session = Depends(get_db),
) -> MfaAktiviertResponse:
    ratelimit.begrenze_ip(request, "mfa", limit=MFA_CODE_PRO_IP[0], fenster_sekunden=MFA_CODE_PRO_IP[1])
    user = db.get(User, token_payload["sub"])
    if user is None or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA wurde noch nicht eingerichtet.")

    secret = decrypt_field(user.mfa_secret_encrypted)
    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: mfa_service.verbrauche_totp(db, user, secret=secret, code=payload.code),
        mandant_id=token_payload["mandant_id"], aktion="mfa_code_falsch", fehlertext="Der Code ist falsch oder abgelaufen.",
    )

    mandant_id = token_payload["mandant_id"]
    erste_aktivierung = not user.mfa_enabled
    user.mfa_enabled = True
    bruteforce.setze_zurueck(user)
    # Nur bei der ersten Aktivierung: zehn Wiederherstellungscodes, die genau jetzt (einmalig) im Klartext zurueckgehen.
    codes = mfa_service.erzeuge_wiederherstellungscodes(db, user, mandant_id=mandant_id) if erste_aktivierung else None
    _, access_token = create_full_session(
        db,
        user=user,
        mandant_id=mandant_id,
        user_agent=request.headers.get("user-agent"),
        remember_device=payload.remember_device,
    )
    record_audit(db, aktion="mfa_aktiviert", mandant_id=mandant_id, user_id=user.id)
    if codes is not None:
        record_audit(db, aktion="mfa_wiederherstellungscodes_erzeugt", mandant_id=mandant_id, user_id=user.id)
    db.commit()
    return MfaAktiviertResponse(access_token=access_token, wiederherstellungscodes=codes)


@router.post("/login", response_model=PreAuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> PreAuthResponse:
    ratelimit.begrenze_ip(request, "login", limit=LOGIN_PRO_IP[0], fenster_sekunden=LOGIN_PRO_IP[1])
    user = _find_user_by_email(db, payload.email)

    if user is not None and bruteforce.ist_gesperrt(user):
        # Do not reveal that the account exists via a different error message (or response time).
        _dummy_passwort_pruefen(payload.password)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    if user is None or user.geloescht_am is not None:
        _dummy_passwort_pruefen(payload.password)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    if not verify_password(payload.password, user.passwort_hash):
        bruteforce.registriere_fehlversuch(db, user, mandant_id=None, aktion="login_fehlgeschlagen")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    mandant_id = mandant_des_nutzers(db, user.id)
    if mandant_id is None:
        # Mitgliedschaft wurde entfernt (siehe /auth/mitglieder/{user_id}/entfernen) --
        # der Account existiert noch, hat aber keinen Zugriff mehr auf einen Mandanten.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    set_rls_mandant(db, mandant_id)
    if not user.mfa_enabled:
        # Mit aktivem MFA bleibt der Zaehler stehen, bis auch der Code stimmt (sonst liesse sich der MFA-Code-Zaehler
        # mit bekanntem Passwort durch erneutes Anmelden immer wieder auf null setzen).
        bruteforce.setze_zurueck(user)
    if password_needs_rehash(user.passwort_hash):
        user.passwort_hash = hash_password(payload.password)
    record_audit(db, aktion="login_erfolgreich", mandant_id=mandant_id, user_id=user.id)
    db.commit()

    if not user.mfa_enabled:
        return _ohne_mfa_anmelden(db, request, user, mandant_id)

    pre_auth_token = create_token(user_id=user.id, scope="pre_mfa", mandant_id=mandant_id, minutes=5, security_version=user.security_version)
    return PreAuthResponse(status="mfa_required", pre_auth_token=pre_auth_token)


@router.post("/login/mfa", response_model=TokenResponse)
def login_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    token_payload: dict = Depends(require_pre_mfa),
    db: Session = Depends(get_db),
) -> TokenResponse:
    ratelimit.begrenze_ip(request, "mfa", limit=MFA_CODE_PRO_IP[0], fenster_sekunden=MFA_CODE_PRO_IP[1])
    user = db.get(User, token_payload["sub"])
    if user is None or not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist fuer dieses Konto nicht aktiv.")

    secret = decrypt_field(user.mfa_secret_encrypted)
    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: mfa_service.verbrauche_totp(db, user, secret=secret, code=payload.code),
        mandant_id=token_payload["mandant_id"], aktion="mfa_code_falsch", fehlertext="Der Code ist falsch oder abgelaufen.",
    )
    bruteforce.setze_zurueck(user)

    _, access_token = create_full_session(
        db,
        user=user,
        mandant_id=token_payload["mandant_id"],
        user_agent=request.headers.get("user-agent"),
        remember_device=payload.remember_device,
    )
    record_audit(db, aktion="sitzung_erstellt", mandant_id=token_payload["mandant_id"], user_id=user.id)
    db.commit()
    return TokenResponse(access_token=access_token)


@router.post("/login/mfa/wiederherstellungscode", response_model=TokenResponse)
def login_mfa_wiederherstellungscode(
    payload: WiederherstellungscodeLoginRequest,
    request: Request,
    token_payload: dict = Depends(require_pre_mfa),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Anmeldung mit einem Wiederherstellungscode statt des TOTP-Codes (z. B. Handy verloren). Der Code wird verbraucht;
    falsche Versuche zaehlen in denselben Fehlversuchszaehler wie TOTP-Codes (app/auth/bruteforce.py)."""
    ratelimit.begrenze_ip(request, "mfa", limit=MFA_CODE_PRO_IP[0], fenster_sekunden=MFA_CODE_PRO_IP[1])
    user = db.get(User, token_payload["sub"])
    if user is None or not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist fuer dieses Konto nicht aktiv.")
    mandant_id = token_payload["mandant_id"]
    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: mfa_service.verbrauche_wiederherstellungscode(db, user, payload.wiederherstellungscode),
        mandant_id=mandant_id, aktion="mfa_wiederherstellungscode_falsch",
        fehlertext="Der Wiederherstellungscode ist falsch oder bereits verwendet.",
    )
    bruteforce.setze_zurueck(user)
    _, access_token = create_full_session(
        db, user=user, mandant_id=mandant_id, user_agent=request.headers.get("user-agent"),
        remember_device=payload.remember_device,
    )
    record_audit(db, aktion="mfa_wiederherstellungscode_verwendet", mandant_id=mandant_id, user_id=user.id,
                 kontext=f"verbleibend:{mfa_service.anzahl_offener_codes(db, user)}")
    record_audit(db, aktion="sitzung_erstellt", mandant_id=mandant_id, user_id=user.id, kontext="wiederherstellungscode")
    db.commit()
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(token_payload: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> None:
    """Beendet die aktuelle Sitzung serverseitig. Ohne diese Route bliebe ein Token nach dem "Abmelden" im Browser bis
    zum Ablauf (bis zu 30 Tage bei "Dieses Geraet merken") gueltig, falls es vorher abgegriffen wurde."""
    sitzung = db.get(AuthSession, token_payload["sid"])
    if sitzung is not None and sitzung.widerrufen_am is None:
        sitzung.widerrufen_am = datetime.now(timezone.utc)
        record_audit(db, aktion="abgemeldet", mandant_id=token_payload["mandant_id"], user_id=token_payload["sub"])
        db.commit()


@router.get("/me", response_model=MeResponse)
def me(token_payload: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> MeResponse:
    mitgliedschaft = (
        db.query(Mitgliedschaft)
        .filter(
            Mitgliedschaft.user_id == token_payload["sub"],
            Mitgliedschaft.mandant_id == token_payload["mandant_id"],
        )
        .first()
    )
    if mitgliedschaft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitgliedschaft nicht gefunden.")
    return MeResponse(
        user_id=mitgliedschaft.user_id,
        mandant_id=mitgliedschaft.mandant_id,
        firmenname=mitgliedschaft.mandant.firmenname,
        rolle=mitgliedschaft.rolle,
    )


@router.post("/passwort/aendern", status_code=status.HTTP_204_NO_CONTENT)
def passwort_aendern(
    payload: PasswortAendernRequest, token_payload: dict = Depends(require_full_auth), db: Session = Depends(get_db)
) -> None:
    """Noetig, damit ein per /mitglieder direkt angelegtes Konto sein Einmal-Passwort
    (siehe create_mitglied) je wieder loswerden kann -- ohne diese Route waere das
    Erstpasswort fuer immer festgeschrieben."""
    user = db.get(User, token_payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden.")
    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: verify_password(payload.aktuelles_passwort, user.passwort_hash),
        mandant_id=token_payload["mandant_id"], aktion="passwort_pruefung_fehlgeschlagen",
        fehlertext="Aktuelles Passwort ist falsch.",
    )

    user.passwort_hash = hash_password(payload.neues_passwort)
    user.passwort_geaendert_am = datetime.now(timezone.utc)
    invalidate_security_context(db, user)
    record_audit(db, aktion="passwort_geaendert", mandant_id=token_payload["mandant_id"], user_id=user.id)
    db.commit()


def _mandant_response(mandant: Mandant) -> MandantResponse:
    return MandantResponse(
        id=mandant.id, firmenname=mandant.firmenname, ust_id=mandant.ust_id, steuernummer=mandant.steuernummer,
        adresse=mandant.adresse, datev_beraternummer=mandant.datev_beraternummer, datev_mandantennummer=mandant.datev_mandantennummer,
        steuerberater_name=mandant.steuerberater_name, steuerberater_email=mandant.steuerberater_email,
        steuerberater_telefon=mandant.steuerberater_telefon,
        rechnungsvorlage=mandant.rechnungsvorlage, akzentfarbe=mandant.akzentfarbe,
        fusszeile_text=mandant.fusszeile_text, hat_logo=mandant.logo_referenz is not None,
        design_variante=mandant.design_variante, logo_groesse=mandant.logo_groesse,
        briefpapier_id=mandant.briefpapier_id, sprache=mandant.sprache, iban=mandant.iban, bic=mandant.bic,
        telefon=mandant.telefon, kontakt_email=mandant.kontakt_email,
        zeige_absenderzeile=mandant.zeige_absenderzeile, zeige_kundennummer=mandant.zeige_kundennummer,
        zeige_kontaktperson=mandant.zeige_kontaktperson, zeige_artikelnummer=mandant.zeige_artikelnummer,
        zeige_positionsbeschreibung=mandant.zeige_positionsbeschreibung, zeige_ust_pro_position=mandant.zeige_ust_pro_position,
        zeige_girocode=mandant.zeige_girocode, zeige_fusszeile=mandant.zeige_fusszeile,
        zeige_seitenzahlen=mandant.zeige_seitenzahlen, zeige_falz_lochmarken=mandant.zeige_falz_lochmarken,
    )


@router.get("/mandant", response_model=MandantResponse)
def get_mandant(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> MandantResponse:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return _mandant_response(mandant)


@router.patch("/mandant", response_model=MandantResponse)
def update_mandant(payload: MandantUpdate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> MandantResponse:
    """Stammdaten des eigenen Mandanten pflegen — u.a. USt-IdNr./Steuernummer, ohne die
    keine E-Rechnung erzeugt werden kann (siehe app/invoices/e_invoice.py)."""
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")

    updates = payload.model_dump(exclude_unset=True)
    # Stamm- und Bankdaten stehen auf jeder Rechnung: Wer sie aendert, kann Zahlungen umleiten (IBAN) oder den
    # Rechnungskopf faelschen. Nur der Owner darf das; Design/Vorlage duerfen alle Mitglieder pflegen.
    geaenderte_stammdaten = [
        feld for feld, wert in updates.items()
        if feld not in DESIGN_FELDER_FUER_MITGLIEDER and (getattr(mandant, feld, None) or None) != (wert or None)
    ]  # unveraenderte Werte (das Design-Formular schickt IBAN/BIC mit) gelten nicht als Aenderung
    if geaenderte_stammdaten and not ist_owner(db, auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Firmen- und Bankdaten darf nur der Owner ändern.")
    if updates.get("briefpapier_id"):
        briefpapier = db.get(Briefpapier, updates["briefpapier_id"])
        if briefpapier is None or briefpapier.mandant_id != mandant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Briefpapier gehoert nicht zu diesem Mandanten.")
    for field, value in updates.items():
        setattr(mandant, field, value)

    record_audit(db, aktion="mandant_aktualisiert", mandant_id=mandant.id, user_id=auth["sub"])
    db.commit()
    return _mandant_response(mandant)


@router.post("/mandant/rechnungsvorlage/vorschau")
def post_rechnungsvorlage_vorschau(
    payload: RechnungsvorlageVorschauRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> Response:
    """Beispiel-PDF mit Beispieldaten, damit jede Design-Einstellung vor dem Speichern
    als echtes PDF beurteilt werden kann. Die Felder im Body ueberschreiben die
    gespeicherten Werte nur fuer dieses eine PDF — es wird bewusst nicht committet.

    Bewusst POST mit JSON-Body: IBAN/BIC/Fusszeile duerfen nicht als Query-Parameter im
    Zugriffslog des Servers landen. Einen GET-Pfad gibt es nicht mehr."""
    vorlage, akzentfarbe, fusszeile_text = payload.vorlage, payload.akzentfarbe, payload.fusszeile_text
    design_variante, logo_groesse, sprache = payload.design_variante, payload.logo_groesse, payload.sprache
    iban, bic = payload.iban, payload.bic
    zeige_absenderzeile, zeige_kundennummer = payload.zeige_absenderzeile, payload.zeige_kundennummer
    zeige_kontaktperson, zeige_artikelnummer = payload.zeige_kontaktperson, payload.zeige_artikelnummer
    zeige_positionsbeschreibung, zeige_ust_pro_position = payload.zeige_positionsbeschreibung, payload.zeige_ust_pro_position
    zeige_girocode, zeige_fusszeile = payload.zeige_girocode, payload.zeige_fusszeile
    zeige_seitenzahlen, zeige_falz_lochmarken = payload.zeige_seitenzahlen, payload.zeige_falz_lochmarken
    # null oder "" heisst "kein Briefpapier"; fehlt das Feld ganz, gilt die gespeicherte Auswahl.
    briefpapier_id = (payload.briefpapier_id or "") if "briefpapier_id" in payload.model_fields_set else None
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")

    overrides = {
        "rechnungsvorlage": vorlage, "akzentfarbe": akzentfarbe, "fusszeile_text": fusszeile_text,
        "design_variante": design_variante, "logo_groesse": logo_groesse, "sprache": sprache,
        "iban": iban, "bic": bic,
        "zeige_absenderzeile": zeige_absenderzeile, "zeige_kundennummer": zeige_kundennummer,
        "zeige_kontaktperson": zeige_kontaktperson, "zeige_artikelnummer": zeige_artikelnummer,
        "zeige_positionsbeschreibung": zeige_positionsbeschreibung, "zeige_ust_pro_position": zeige_ust_pro_position,
        "zeige_girocode": zeige_girocode, "zeige_fusszeile": zeige_fusszeile,
        "zeige_seitenzahlen": zeige_seitenzahlen, "zeige_falz_lochmarken": zeige_falz_lochmarken,
    }
    if briefpapier_id is not None:
        briefpapier = db.get(Briefpapier, briefpapier_id) if briefpapier_id else None
        if briefpapier_id and (briefpapier is None or briefpapier.mandant_id != mandant.id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Briefpapier gehoert nicht zu diesem Mandanten.")
        mandant.briefpapier = briefpapier
    for feld, wert in overrides.items():
        if wert is not None:
            setattr(mandant, feld, wert)

    positionen = [
        DocumentPosition(beschreibung="Beratungsleistung", menge=Decimal("2"), einzelpreis=Decimal("450.00"), ust_satz=Decimal("19.00"), artikelnummer="ART-001"),
        DocumentPosition(beschreibung="Reisekosten", menge=Decimal("1"), einzelpreis=Decimal("120.00"), ust_satz=Decimal("19.00"), artikelnummer="ART-002"),
    ]
    netto = Decimal("1020.00")
    ust = Decimal("193.80")
    pdf = render_document_pdf(
        mandant, titel_prefix="rechnung", nummer="RE-2026-0001", ist_entwurf=False, entwurf_hinweis="",
        kontakt_name="Beispiel Kunde GmbH", kontakt_strasse="Musterstraße 1", kontakt_ort_zeile="12345 Musterstadt",
        kontakt_land="DE", datum_label="leistungsdatum", datum=date.today(), folgedatum_label="zahlungsziel",
        folgedatum=date.today(), positionen=positionen, waehrung="EUR", netto_gesamt=netto, ust_gesamt=ust,
        brutto_gesamt=netto + ust, kundennummer="K-1000", kontaktperson="Max Mustermann",
    )
    return Response(content=pdf, media_type="application/pdf")


@router.post("/mandant/logo", response_model=MandantResponse)
def upload_logo(file: UploadFile = File(...), auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> MandantResponse:
    # Begrenzt lesen: ohne Grenze liesse sich der Arbeitsspeicher mit einem riesigen Upload fuellen.
    data = file.file.read(branding_storage.MAX_BYTES + 1)
    if len(data) > branding_storage.MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Logo ist zu gross (maximal 2 MB).")
    try:
        mime_type = pruefe_bild(data, branding_storage.ALLOWED_MIME_TYPES.keys())
    except UngueltigesBild as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")

    mandant.logo_referenz = branding_storage.save(mandant.id, mime_type, data)
    record_audit(db, aktion="logo_hochgeladen", mandant_id=mandant.id, user_id=auth["sub"])
    db.commit()
    return _mandant_response(mandant)


@router.delete("/mandant/logo", response_model=MandantResponse)
def delete_logo(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> MandantResponse:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")

    mandant.logo_referenz = None
    record_audit(db, aktion="logo_entfernt", mandant_id=mandant.id, user_id=auth["sub"])
    db.commit()
    return _mandant_response(mandant)


@router.get("/mandant/logo")
def get_logo(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None or mandant.logo_referenz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein Logo hinterlegt.")

    extension = mandant.logo_referenz.rsplit(".", 1)[-1]
    media_type = "image/jpeg" if extension == "jpg" else f"image/{extension}"
    return Response(content=branding_storage.read(mandant.logo_referenz), media_type=media_type)


@router.get("/briefpapier", response_model=list[BriefpapierResponse])
def list_briefpapier(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[BriefpapierResponse]:
    eintraege = (
        db.query(Briefpapier)
        .filter(Briefpapier.mandant_id == auth["mandant_id"])
        .order_by(Briefpapier.name)
        .all()
    )
    return [BriefpapierResponse(id=b.id, name=b.name) for b in eintraege]


@router.post("/briefpapier", response_model=BriefpapierResponse, status_code=status.HTTP_201_CREATED)
def create_briefpapier(
    name: str = Form(...), file: UploadFile = File(...), auth=Depends(require_full_auth), db: Session = Depends(get_db),
) -> BriefpapierResponse:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    data = file.file.read(letterhead_storage.MAX_BYTES + 1)
    if len(data) > letterhead_storage.MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datei ist zu gross (maximal 5 MB).")
    try:
        mime_type = pruefe_bild(data, letterhead_storage.ALLOWED_MIME_TYPES.keys())
    except UngueltigesBild as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    briefpapier = Briefpapier(
        mandant_id=auth["mandant_id"], name=name.strip() or "Briefpapier",
        datei_referenz=letterhead_storage.save(auth["mandant_id"], mime_type, data),
    )
    db.add(briefpapier)
    record_audit(db, aktion="briefpapier_hochgeladen", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=briefpapier.name)
    db.commit()
    return BriefpapierResponse(id=briefpapier.id, name=briefpapier.name)


@router.delete("/briefpapier/{briefpapier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_briefpapier(briefpapier_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> None:
    briefpapier = get_scoped_or_404(db, Briefpapier, briefpapier_id, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is not None and mandant.briefpapier_id == briefpapier.id:
        mandant.briefpapier_id = None
    db.delete(briefpapier)
    record_audit(db, aktion="briefpapier_entfernt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=briefpapier.name)
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def request_deletion(
    payload: KontoLoeschenRequest,
    token_payload: dict = Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> None:
    """Anonymizes personal master data. Does not remove the row or any booking-related
    data linked to it — those stay under the GoBD/§147 AO retention duty (see
    projekt-buchhaltung-ki.md, Compliance-Leitplanken).

    Unumkehrbar, deshalb nicht allein mit einem (gestohlenen) Token moeglich: Passwort und -- bei aktivem MFA --
    der aktuelle Code sind Pflicht. Fehlversuche zaehlen im gemeinsamen Brute-Force-Zaehler des Kontos
    (app/auth/bruteforce.py); nach zu vielen Fehlversuchen ist das Konto vorübergehend gesperrt."""
    user = db.get(User, token_payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden.")

    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: verify_password(payload.passwort, user.passwort_hash),
        mandant_id=token_payload["mandant_id"], aktion="passwort_pruefung_fehlgeschlagen",
        fehlertext="Passwort ist falsch.",
    )
    if user.mfa_enabled and user.mfa_secret_encrypted is not None:
        if payload.mfa_code is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der aktuelle MFA-Code ist erforderlich.")
        secret = decrypt_field(user.mfa_secret_encrypted)
        bruteforce.pruefe_geheimnis(
            db, user, ist_korrekt=lambda: mfa_service.verbrauche_totp(db, user, secret=secret, code=payload.mfa_code.strip()),
            mandant_id=token_payload["mandant_id"], aktion="mfa_code_falsch", fehlertext="MFA-Code ist ungueltig.",
        )
    bruteforce.setze_zurueck(user)

    anonym_marker = f"geloescht-{user.id}@anonymisiert.invalid"
    user.email_encrypted = encrypt_field(anonym_marker)
    user.email_lookup_hash = lookup_hash(anonym_marker)
    user.passwort_hash = hash_password(secrets.token_urlsafe(32))  # unguessable, login is disabled from here on
    user.mfa_secret_encrypted = None
    user.mfa_enabled = False
    user.mfa_letzter_zeitschritt = None
    mfa_service.loesche_wiederherstellungscodes(db, user)
    db.query(PasswortResetToken).filter(PasswortResetToken.user_id == user.id).delete(synchronize_session=False)
    user.geloescht_am = datetime.now(timezone.utc)

    record_audit(db, aktion="loeschantrag", mandant_id=token_payload["mandant_id"], user_id=user.id)
    db.commit()


@router.get("/datenexport")
def datenexport(auth: dict = Depends(require_owner), db: Session = Depends(get_db)) -> Response:
    """DSGVO-Datenauskunft/-export (Art. 15/20) als herunterladbare JSON-Datei.

    Owner-only: der Export enthaelt alle Mandantendaten inkl. aller Mitglieder und
    Kontakte, nicht nur die des aufrufenden Nutzers. Verschluesselte Felder werden
    entschluesselt ausgegeben, Sicherheitsmaterial (Passwort-Hashes, MFA-Secrets,
    Lookup-Hashes) bewusst nicht (siehe app/auth/datenexport.py)."""
    export = erstelle_datenexport(db, auth["mandant_id"])
    record_audit(db, aktion="datenexport", mandant_id=auth["mandant_id"], user_id=auth["sub"])
    db.commit()
    inhalt = json.dumps(export, ensure_ascii=False, indent=2)
    dateiname = f"bilantiq-datenexport-{date.today().isoformat()}.json"
    return Response(
        content=inhalt,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


EINLADUNG_GUELTIGKEIT_TAGE = 7


def _einladung_response(einladung: Einladung) -> EinladungResponse:
    return EinladungResponse(
        id=einladung.id, code=einladung.code, rolle=einladung.rolle,
        ablauf_am=einladung.ablauf_am.isoformat(),
        eingeloest_am=einladung.eingeloest_am.isoformat() if einladung.eingeloest_am else None,
        widerrufen=einladung.widerrufen,
    )


@router.post("/einladungen", response_model=EinladungResponse, status_code=status.HTTP_201_CREATED)
def create_einladung(payload: EinladungCreate, auth=Depends(require_owner), db: Session = Depends(get_db)) -> EinladungResponse:
    """Kein E-Mail-Versand -- der Code wird manuell weitergegeben (siehe Einladung-
    Docstring). Nur der Owner darf einladen, damit nicht jedes Mitglied beliebig
    weitere Zugaenge zum Mandanten erzeugen kann."""
    mandant = sperre_mandant(db, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    code = secrets.token_hex(6).upper()  # 48 Bit (vorher 32): macht Durchprobieren zusaetzlich zum IP-Limit aussichtslos
    ablauf = datetime.now(timezone.utc) + timedelta(days=EINLADUNG_GUELTIGKEIT_TAGE)
    einladung = Einladung(mandant_id=auth["mandant_id"], code=code, rolle=payload.rolle, erstellt_von=auth["sub"], ablauf_am=ablauf)
    db.add(einladung)
    record_audit(db, aktion="einladung_erstellt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=payload.rolle)
    db.commit()
    return _einladung_response(einladung)


@router.get("/einladungen", response_model=list[EinladungResponse])
def list_einladungen(auth=Depends(require_owner), db: Session = Depends(get_db)) -> list[EinladungResponse]:
    einladungen = (
        db.query(Einladung)
        .filter(Einladung.mandant_id == auth["mandant_id"])
        .order_by(Einladung.erstellt_am.desc())
        .all()
    )
    return [_einladung_response(e) for e in einladungen]


@router.post("/einladungen/{einladung_id}/widerrufen", response_model=EinladungResponse)
def widerrufe_einladung(einladung_id: str, auth=Depends(require_owner), db: Session = Depends(get_db)) -> EinladungResponse:
    einladung = get_scoped_or_404(db, Einladung, einladung_id, auth["mandant_id"])
    einladung.widerrufen = True
    db.commit()
    return _einladung_response(einladung)


@router.post("/mitglieder", response_model=MitgliedCreateResponse, status_code=status.HTTP_201_CREATED)
def create_mitglied(payload: MitgliedCreate, auth=Depends(require_owner), db: Session = Depends(get_db)) -> MitgliedCreateResponse:
    """Legt einen Nutzer direkt an, statt ueber einen Einladungscode (siehe
    create_einladung) -- der Owner setzt das Erstpasswort weiter, es gibt weiterhin
    keinen E-Mail-Versand im Projekt. Das Konto durchlaeuft beim ersten Login ganz
    normal die Pflicht-MFA-Einrichtung wie jedes andere (siehe login())."""
    mandant = sperre_mandant(db, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    if _find_user_by_email(db, payload.email) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diese E-Mail wird bereits verwendet.")

    initial_passwort = secrets.token_urlsafe(12)
    user = User(
        email_encrypted=encrypt_field(payload.email),
        email_lookup_hash=lookup_hash(payload.email),
        passwort_hash=hash_password(initial_passwort),
    )
    db.add(user)
    db.flush()

    mitgliedschaft = Mitgliedschaft(user_id=user.id, mandant_id=auth["mandant_id"], rolle=payload.rolle)
    db.add(mitgliedschaft)
    record_audit(db, aktion="mitglied_direkt_angelegt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=payload.rolle)
    db.commit()

    return MitgliedCreateResponse(user_id=user.id, email=payload.email, rolle=payload.rolle, initial_passwort=initial_passwort)


@router.get("/mitglieder", response_model=list[MitgliedResponse])
def list_mitglieder(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[MitgliedResponse]:
    mitgliedschaften = db.query(Mitgliedschaft).filter(Mitgliedschaft.mandant_id == auth["mandant_id"]).all()
    return [
        MitgliedResponse(user_id=m.user_id, email=decrypt_field(m.user.email_encrypted), rolle=m.rolle)
        for m in mitgliedschaften
    ]


@router.post("/mitglieder/{user_id}/entfernen", status_code=status.HTTP_204_NO_CONTENT)
def entferne_mitglied(user_id: str, auth=Depends(require_owner), db: Session = Depends(get_db)) -> None:
    if user_id == auth["sub"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der Owner kann sich nicht selbst entfernen.")
    mitgliedschaft = (
        db.query(Mitgliedschaft)
        .filter(Mitgliedschaft.user_id == user_id, Mitgliedschaft.mandant_id == auth["mandant_id"])
        .first()
    )
    if mitgliedschaft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitglied nicht gefunden.")
    db.delete(mitgliedschaft)
    record_audit(db, aktion="mitglied_entfernt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=user_id)
    db.commit()


# Passwort vergessen/zuruecksetzen: Logik in app/auth/passwort_reset.py, hier am Auth-Router registriert (oeffentlich).
router.post("/passwort/vergessen", response_model=PasswortVergessenResponse, status_code=status.HTTP_202_ACCEPTED)(
    passwort_reset.passwort_vergessen
)
router.post("/passwort/zuruecksetzen", status_code=status.HTTP_204_NO_CONTENT)(passwort_reset.passwort_zuruecksetzen)
