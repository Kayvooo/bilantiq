"""Zweiter Faktor: einmal verbrauchbare TOTP-Codes (Replay-Schutz) und Wiederherstellungscodes.

TOTP-Replay-Schutz: Pro Konto wird der zuletzt akzeptierte Zeitschritt gespeichert (``User.mfa_letzter_zeitschritt``).
Ein Code wird nur akzeptiert, wenn sein Zeitschritt groesser ist. Das Speichern geschieht als bedingtes UPDATE
(``... WHERE mfa_letzter_zeitschritt IS NULL OR mfa_letzter_zeitschritt < :schritt``), damit zwei gleichzeitige Anfragen mit
demselben Code nicht beide durchkommen; die zweite sieht 0 betroffene Zeilen. Gilt fuer Anmeldung, Einrichtung, Deaktivieren
und Neu-Einrichten.

Wiederherstellungscodes: 10 Einmalcodes (``XXXXX-XXXXX``, 32er-Alphabet ohne I/O, ca. 50 Bit Entropie) als Ersatz fuer den
TOTP-Code, wenn das Geraet verloren ist. In der Datenbank steht nur der HMAC-SHA256 (``blind_index`` mit Nutzer-bezogenem
Zweck, Schluessel aus BLIND_INDEX_SECRET). Argon2 waere hier ueberfluessig: Die Codes sind zufaellig und nicht vom Menschen
gewaehlt, ein Angreifer ohne Serverschluessel kann den Hash nicht offline durchprobieren, und online greifen die Sperren aus
``app/auth/bruteforce.py``. Der Klartext wird genau einmal zurueckgegeben (bei Erzeugung) und nie protokolliert.
"""
from __future__ import annotations

import hmac
import re
import secrets
from datetime import datetime, timezone

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.auth.models import MfaWiederherstellungscode, User
from app.core.key_management import blind_index
from app.core.security import pruefe_mfa_zeitschritt

ANZAHL_WIEDERHERSTELLUNGSCODES = 10
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # 32 Zeichen, ohne 0/1/I/O (Verwechslungsgefahr)
_GRUPPE = 5
_TOTP_FORMAT = re.compile(r"^\d{6}$")


def ist_totp_format(code: str) -> bool:
    return bool(_TOTP_FORMAT.fullmatch(code.strip()))


def verbrauche_totp(db: Session, user: User, *, secret: str, code: str) -> bool:
    """True, wenn der Code gueltig und noch nicht verbraucht ist; er ist dann (bis zum Commit des Aufrufers) verbraucht."""
    schritt = pruefe_mfa_zeitschritt(secret=secret, code=code.strip(), letzter_zeitschritt=user.mfa_letzter_zeitschritt)
    if schritt is None:
        return False
    return _zeitschritt_festhalten(db, user, schritt)


def _zeitschritt_festhalten(db: Session, user: User, schritt: int) -> bool:
    ergebnis = db.execute(
        update(User)
        .where(User.id == user.id, or_(User.mfa_letzter_zeitschritt.is_(None), User.mfa_letzter_zeitschritt < schritt))
        .values(mfa_letzter_zeitschritt=schritt)
        .execution_options(synchronize_session=False)
    )
    if ergebnis.rowcount != 1:
        return False
    user.mfa_letzter_zeitschritt = schritt
    return True


def pruefe_totp_ohne_verbrauch(secret: str, code: str) -> int | None:
    """Fuer ein noch nicht aktives (ausstehendes) Secret: Zeitschritt des Codes oder None. Ein Replay-Schutz ist hier
    nicht noetig; der Zeitschritt wird nach dem Umschalten des Secrets mit ``setze_verbrauchten_zeitschritt`` festgehalten."""
    return pruefe_mfa_zeitschritt(secret=secret, code=code.strip(), letzter_zeitschritt=None)


def setze_verbrauchten_zeitschritt(user: User, schritt: int | None) -> None:
    user.mfa_letzter_zeitschritt = schritt


# ---------------------------------------------------------------------------
# Wiederherstellungscodes


def normalisiere_code(eingabe: str) -> str:
    return re.sub(r"[\s\-]", "", eingabe).upper()


def _hash(user_id: str, normalisiert: str) -> str:
    return blind_index(normalisiert, purpose=f"mfa-recovery:{user_id}")


def _neuer_code() -> str:
    zeichen = "".join(secrets.choice(_ALPHABET) for _ in range(2 * _GRUPPE))
    return f"{zeichen[:_GRUPPE]}-{zeichen[_GRUPPE:]}"


def erzeuge_wiederherstellungscodes(db: Session, user: User, *, mandant_id: str) -> list[str]:
    """Ersetzt ALLE bisherigen Codes des Kontos durch zehn neue und gibt die Klartexte zurueck (einmalig). Kein Commit."""
    db.query(MfaWiederherstellungscode).filter(MfaWiederherstellungscode.user_id == user.id).delete(synchronize_session=False)
    codes: list[str] = []
    while len(codes) < ANZAHL_WIEDERHERSTELLUNGSCODES:
        code = _neuer_code()
        if code not in codes:
            codes.append(code)
    for code in codes:
        db.add(MfaWiederherstellungscode(user_id=user.id, mandant_id=mandant_id, code_hash=_hash(user.id, normalisiere_code(code))))
    db.flush()
    return codes


def loesche_wiederherstellungscodes(db: Session, user: User) -> None:
    db.query(MfaWiederherstellungscode).filter(MfaWiederherstellungscode.user_id == user.id).delete(synchronize_session=False)


def anzahl_offener_codes(db: Session, user: User) -> int:
    return (
        db.query(MfaWiederherstellungscode)
        .filter(MfaWiederherstellungscode.user_id == user.id, MfaWiederherstellungscode.verbraucht_am.is_(None))
        .count()
    )


def verbrauche_wiederherstellungscode(db: Session, user: User, eingabe: str) -> bool:
    """True, wenn der Code zu einem noch nicht verbrauchten Code des Kontos passt; er ist dann (bis zum Commit) verbraucht."""
    gesucht = _hash(user.id, normalisiere_code(eingabe)).encode()
    offene = (
        db.query(MfaWiederherstellungscode)
        .filter(MfaWiederherstellungscode.user_id == user.id, MfaWiederherstellungscode.verbraucht_am.is_(None))
        .all()
    )
    treffer: MfaWiederherstellungscode | None = None
    for zeile in offene:  # alle vergleichen, kein vorzeitiger Abbruch
        if hmac.compare_digest(zeile.code_hash.encode(), gesucht):
            treffer = zeile
    if treffer is None:
        return False
    ergebnis = db.execute(
        update(MfaWiederherstellungscode)
        .where(MfaWiederherstellungscode.id == treffer.id, MfaWiederherstellungscode.verbraucht_am.is_(None))
        .values(verbraucht_am=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    return ergebnis.rowcount == 1
