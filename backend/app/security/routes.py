import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import bruteforce, mfa_service
from app.auth.dependencies import require_full_auth
from app.auth.mfa_richtlinie import mfa_erforderlich
from app.auth.models import AuthSession, EmailAenderung, Mitgliedschaft, User
from app.auth.security_service import invalidate_security_context, revoke_sessions
from app.config import settings
from app.core import mailer, ratelimit
from app.core.audit_log import record as record_audit
from app.core.crypto import decrypt_field, encrypt_field, lookup_hash
from app.core.key_management import blind_index
from app.core.security import generate_mfa_secret, mfa_provisioning_uri, verify_password
from app.db import get_db
from app.security.schemas import (
    EmailChangeConfirmRequest,
    EmailChangeStartRequest,
    MfaBestaetigtResponse,
    MfaResetConfirmRequest,
    MfaResetStartRequest,
    MfaResetStartResponse,
    SecurityOverviewResponse,
    WiederherstellungscodesResponse,
    SessionResponse,
)

router = APIRouter(prefix="/security", tags=["security"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _pruefe_passwort_und_code(db: Session, user: User, payload: MfaResetStartRequest, mandant_id: str) -> None:
    """Passwort UND aktueller MFA-Code, beides mit gemeinsamem Fehlversuchszaehler (siehe app/auth/bruteforce.py):
    ohne ihn liesse sich der Code bei bekanntem Passwort ueber diese Routen durchprobieren.

    Der "aktuelle Code" ist ein TOTP-Code (einmal verbrauchbar, Replay-Schutz) ODER ein Wiederherstellungscode: Wer sein
    Geraet verloren hat und sich damit angemeldet hat, muss den zweiten Faktor neu einrichten koennen."""
    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: verify_password(payload.aktuelles_passwort, user.passwort_hash),
        mandant_id=mandant_id, aktion="passwort_pruefung_fehlgeschlagen", fehlertext="Aktuelles Passwort ist falsch.",
    )
    secret = decrypt_field(user.mfa_secret_encrypted)
    eingabe = payload.aktueller_code.strip()
    if mfa_service.ist_totp_format(eingabe):
        bruteforce.pruefe_geheimnis(
            db, user, ist_korrekt=lambda: mfa_service.verbrauche_totp(db, user, secret=secret, code=eingabe),
            mandant_id=mandant_id, aktion="mfa_code_falsch", fehlertext="Aktueller MFA-Code ist ungueltig.",
        )
    else:
        bruteforce.pruefe_geheimnis(
            db, user, ist_korrekt=lambda: mfa_service.verbrauche_wiederherstellungscode(db, user, eingabe),
            mandant_id=mandant_id, aktion="mfa_wiederherstellungscode_falsch",
            fehlertext="Aktueller MFA-Code oder Wiederherstellungscode ist ungueltig.",
        )
        record_audit(db, aktion="mfa_wiederherstellungscode_verwendet", mandant_id=mandant_id, user_id=user.id, kontext="sicherheitsaktion")
    bruteforce.setze_zurueck(user)


@router.get("", response_model=SecurityOverviewResponse)
def overview(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> SecurityOverviewResponse:
    user = db.get(User, auth["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden.")
    now = _now()
    sessions = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user.id,
            AuthSession.widerrufen_am.is_(None),
            AuthSession.laeuft_ab_am > now,
        )
        .order_by(AuthSession.erstellt_am.desc())
        .all()
    )
    return SecurityOverviewResponse(
        email=decrypt_field(user.email_encrypted),
        mfa_enabled=user.mfa_enabled,
        wiederherstellungscodes_offen=mfa_service.anzahl_offener_codes(db, user) if user.mfa_enabled else None,
        passwort_geaendert_am=user.passwort_geaendert_am,
        email_geaendert_am=user.email_geaendert_am,
        sessions=[
            SessionResponse(
                id=session.id,
                aktuell=session.id == auth.get("sid"),
                user_agent=session.user_agent,
                erstellt_am=session.erstellt_am,
                laeuft_ab_am=session.laeuft_ab_am,
            )
            for session in sessions
        ],
    )


@router.post("/email/aenderung-starten", status_code=status.HTTP_204_NO_CONTENT)
def start_email_change(
    payload: EmailChangeStartRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> None:
    if not settings.email_aktiv:
        # Die Adresse laesst sich nur mit Code aus einer Bestaetigungsmail aendern; ohne SMTP ginge das nie.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=mailer.EMAIL_NICHT_EINGERICHTET)
    user = db.get(User, auth["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden.")
    # Verhindert Mail-Spam an fremde Adressen ueber diese Route (pro Konto, nicht pro IP).
    ratelimit.begrenze(f"email-aenderung:{user.id}", limit=5, fenster_sekunden=3600)
    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=lambda: verify_password(payload.aktuelles_passwort, user.passwort_hash),
        mandant_id=auth["mandant_id"], aktion="passwort_pruefung_fehlgeschlagen", fehlertext="Aktuelles Passwort ist falsch.",
    )

    new_email = str(payload.neues_email).strip().lower()
    if lookup_hash(new_email) == user.email_lookup_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Das ist bereits deine aktuelle E-Mail-Adresse.")
    if db.query(User).filter(User.email_lookup_hash == lookup_hash(new_email)).first() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diese E-Mail-Adresse kann nicht verwendet werden.")

    db.query(EmailAenderung).filter(EmailAenderung.user_id == user.id).delete(synchronize_session=False)
    code = f"{secrets.randbelow(1_000_000):06d}"
    item = EmailAenderung(
        user_id=user.id,
        mandant_id=auth["mandant_id"],
        neue_email=new_email,
        neue_email_lookup_hash=lookup_hash(new_email),
        code_hash=blind_index(code, purpose=f"email-change:{user.id}"),
        ablauf_am=_now() + timedelta(minutes=15),
    )
    db.add(item)
    try:
        mailer.sende_text_email(
            new_email,
            "Bilantiq: E-Mail-Adresse bestaetigen",
            (
                f"Dein Bestaetigungscode lautet: {code}\n\n"
                "Der Code ist 15 Minuten gueltig. Wenn du die Aenderung nicht angefordert hast, "
                "kannst du diese Nachricht ignorieren."
            ),
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Bestaetigungsmail konnte nicht versendet werden.",
        ) from exc
    record_audit(db, aktion="email_aenderung_gestartet", mandant_id=auth["mandant_id"], user_id=user.id)
    db.commit()


@router.post("/email/aenderung-bestaetigen", status_code=status.HTTP_204_NO_CONTENT)
def confirm_email_change(
    payload: EmailChangeConfirmRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> None:
    user = db.get(User, auth["sub"])
    item = (
        db.query(EmailAenderung)
        .filter(EmailAenderung.user_id == auth["sub"])
        .order_by(EmailAenderung.erstellt_am.desc())
        .first()
    )
    if user is None or item is None or _aware(item.ablauf_am) <= _now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bestaetigungscode ist ungueltig oder abgelaufen.")
    if item.versuche >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Zu viele Fehlversuche. Bitte starte die Aenderung erneut.")

    expected = item.code_hash
    actual = blind_index(payload.code, purpose=f"email-change:{user.id}")
    if not hmac.compare_digest(expected, actual):
        item.versuche += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bestaetigungscode ist ungueltig oder abgelaufen.")

    if db.query(User).filter(User.email_lookup_hash == item.neue_email_lookup_hash, User.id != user.id).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Diese E-Mail-Adresse kann nicht verwendet werden.")

    user.email_encrypted = encrypt_field(item.neue_email)
    user.email_lookup_hash = item.neue_email_lookup_hash
    user.email_geaendert_am = _now()
    invalidate_security_context(db, user)
    db.query(EmailAenderung).filter(EmailAenderung.user_id == user.id).delete(synchronize_session=False)
    record_audit(db, aktion="email_geaendert", mandant_id=auth["mandant_id"], user_id=user.id)
    db.commit()


@router.post("/sessions/andere-abmelden", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> None:
    revoke_sessions(db, user_id=auth["sub"], except_session_id=auth.get("sid"))
    record_audit(db, aktion="andere_sitzungen_abgemeldet", mandant_id=auth["mandant_id"], user_id=auth["sub"])
    db.commit()


@router.post("/sessions/{session_id}/abmelden", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> None:
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != auth["sub"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitzung nicht gefunden.")
    if session.id == auth.get("sid"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Die aktuelle Sitzung kann hier nicht abgemeldet werden.")
    session.widerrufen_am = _now()
    record_audit(db, aktion="sitzung_abgemeldet", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=session.id)
    db.commit()


@router.post("/mfa/einrichten", response_model=MfaResetStartResponse)
def start_mfa_setup(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> MfaResetStartResponse:
    """Erste Einrichtung der Zwei-Faktor-Anmeldung aus einer laufenden Sitzung (MFA ist optional).
    Bestaetigt wird mit /mfa/neu-einrichten/bestaetigen, erst dann ist MFA aktiv."""
    user = db.get(User, auth["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden.")
    if user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist bereits eingerichtet.")
    secret = generate_mfa_secret()
    user.mfa_pending_secret_encrypted = encrypt_field(secret)
    user.mfa_pending_erstellt_am = _now()
    db.commit()
    return MfaResetStartResponse(
        secret=secret,
        provisioning_uri=mfa_provisioning_uri(secret=secret, email=decrypt_field(user.email_encrypted)),
    )


@router.post("/mfa/deaktivieren", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_mfa(
    payload: MfaResetStartRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> None:
    """Schaltet die Zwei-Faktor-Anmeldung wieder ab. Passwort UND aktueller Code sind Pflicht, danach werden alle
    Sitzungen widerrufen und die Anmeldung erfolgt neu (ohne zweiten Faktor)."""
    user = db.get(User, auth["sub"])
    if user is None or not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist nicht eingerichtet.")
    mitgliedschaft = (
        db.query(Mitgliedschaft)
        .filter(Mitgliedschaft.user_id == user.id, Mitgliedschaft.mandant_id == auth["mandant_id"])
        .first()
    )
    if mitgliedschaft is not None and mfa_erforderlich(mitgliedschaft.rolle):
        # Pflicht-MFA (docs/specs/mfa-pflicht.md): Abschalten waere nur ein Umweg ueber die erzwungene Neueinrichtung.
        # Ein anderes Geraet geht ueber /security/mfa/neu-einrichten.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Für deine Rolle ist die Zwei-Faktor-Anmeldung verpflichtend und kann nicht abgeschaltet werden. Du kannst sie neu einrichten.",
        )
    _pruefe_passwort_und_code(db, user, payload, auth["mandant_id"])

    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_erstellt_am = None
    user.mfa_letzter_zeitschritt = None
    mfa_service.loesche_wiederherstellungscodes(db, user)
    invalidate_security_context(db, user)
    record_audit(db, aktion="mfa_deaktiviert", mandant_id=auth["mandant_id"], user_id=user.id)
    db.commit()


@router.post("/mfa/neu-einrichten", response_model=MfaResetStartResponse)
def start_mfa_reset(
    payload: MfaResetStartRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> MfaResetStartResponse:
    user = db.get(User, auth["sub"])
    if user is None or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist nicht eingerichtet.")
    _pruefe_passwort_und_code(db, user, payload, auth["mandant_id"])

    secret = generate_mfa_secret()
    user.mfa_pending_secret_encrypted = encrypt_field(secret)
    user.mfa_pending_erstellt_am = _now()
    db.commit()
    return MfaResetStartResponse(
        secret=secret,
        provisioning_uri=mfa_provisioning_uri(secret=secret, email=decrypt_field(user.email_encrypted)),
    )


@router.post("/mfa/neu-einrichten/bestaetigen", response_model=MfaBestaetigtResponse)
def confirm_mfa_reset(
    payload: MfaResetConfirmRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> MfaBestaetigtResponse:
    """Schliesst die (Neu-)Einrichtung ab. Bei der ERSTEN Aktivierung kommen die zehn Wiederherstellungscodes einmalig im
    Klartext zurueck; bei einer Neu-Einrichtung bleiben die vorhandenen Codes gueltig (sie haengen nicht am Secret)."""
    user = db.get(User, auth["sub"])
    if (
        user is None
        or user.mfa_pending_secret_encrypted is None
        or user.mfa_pending_erstellt_am is None
        or _aware(user.mfa_pending_erstellt_am) + timedelta(minutes=15) <= _now()
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine gueltige MFA-Neueinrichtung aktiv.")
    pending = decrypt_field(user.mfa_pending_secret_encrypted)
    treffer: dict[str, int] = {}

    def _stimmt() -> bool:
        schritt = mfa_service.pruefe_totp_ohne_verbrauch(pending, payload.code)
        if schritt is None:
            return False
        treffer["schritt"] = schritt
        return True

    bruteforce.pruefe_geheimnis(
        db, user, ist_korrekt=_stimmt,
        mandant_id=auth["mandant_id"], aktion="mfa_code_falsch", fehlertext="Der neue MFA-Code ist ungueltig.",
    )
    erste_aktivierung = not user.mfa_enabled
    user.mfa_secret_encrypted = encrypt_field(pending)
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_erstellt_am = None
    user.mfa_enabled = True
    # Der gerade benutzte Code gehoert jetzt zum aktiven Secret und darf nicht erneut zum Anmelden dienen.
    mfa_service.setze_verbrauchten_zeitschritt(user, treffer["schritt"])
    codes = mfa_service.erzeuge_wiederherstellungscodes(db, user, mandant_id=auth["mandant_id"]) if erste_aktivierung else None
    invalidate_security_context(db, user)
    record_audit(db, aktion="mfa_neu_eingerichtet", mandant_id=auth["mandant_id"], user_id=user.id)
    if codes is not None:
        record_audit(db, aktion="mfa_wiederherstellungscodes_erzeugt", mandant_id=auth["mandant_id"], user_id=user.id)
    db.commit()
    return MfaBestaetigtResponse(wiederherstellungscodes=codes)


@router.post("/mfa/wiederherstellungscodes/neu", response_model=WiederherstellungscodesResponse)
def regenerate_recovery_codes(
    payload: MfaResetStartRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> WiederherstellungscodesResponse:
    """Erzeugt zehn neue Wiederherstellungscodes; ALLE bisherigen werden damit ungueltig. Passwort UND aktueller Code
    (TOTP oder ein noch gueltiger Wiederherstellungscode) sind Pflicht. Andere Sitzungen bleiben bestehen: Die Aktion
    aendert nur Ersatz-Codes, nicht den Zugang selbst."""
    user = db.get(User, auth["sub"])
    if user is None or not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist nicht eingerichtet.")
    _pruefe_passwort_und_code(db, user, payload, auth["mandant_id"])
    codes = mfa_service.erzeuge_wiederherstellungscodes(db, user, mandant_id=auth["mandant_id"])
    record_audit(db, aktion="mfa_wiederherstellungscodes_erneuert", mandant_id=auth["mandant_id"], user_id=user.id)
    db.commit()
    return WiederherstellungscodesResponse(wiederherstellungscodes=codes)
