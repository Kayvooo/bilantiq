#!/usr/bin/env python3
"""Wiederherstellungsweg fuer Betreiber: Passwort (und optional MFA) eines Kontos auf dem Server zuruecksetzen.

Wozu: Auf einer Instanz ohne E-Mail-Versand (SMTP optional) gibt es kein "Passwort vergessen" per Link. Wer sein
Passwort verliert, waere sonst dauerhaft ausgesperrt. Die Person, die den Server betreibt, kann hier ein neues
Passwort setzen. Das Skript braucht Zugriff auf Datenbank und Schluessel der Instanz (dieselbe Umgebung wie das
Backend), es gibt keinen Netzwerkzugang dafuer.

Aufruf (im Backend-Container bzw. mit denselben Umgebungsvariablen/Secrets)::

    docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend \\
        python -m scripts.konto_wiederherstellen --email name@example.org

    --konten-auflisten      zeigt die E-Mail-Adressen aller Konten (falls die Adresse vergessen wurde)
    --zufallspasswort       erzeugt ein Passwort und gibt es einmal aus (sonst: verdeckte Eingabe, zweimal)
    --mfa-zuruecksetzen     schaltet zusaetzlich die Zwei-Faktor-Anmeldung ab und loescht die Wiederherstellungscodes

Wirkung: neues Passwort (Argon2id), Fehlversuchszaehler und Kontosperre zurueckgesetzt, alle Sitzungen widerrufen,
offene Passwort-Reset-Links entwertet, Audit-Eintrag ``konto_wiederhergestellt_betreiber`` (ohne Passwort).
Ohne ``--mfa-zuruecksetzen`` bleibt MFA aktiv; wer Geraet und Wiederherstellungscodes verloren hat, braucht die Option.

Sicherheitshinweis: Wer dieses Skript ausfuehren kann, kann jedes Konto uebernehmen. Das ist beabsichtigt (Betreiber
haben ohnehin Zugriff auf Datenbank und Schluessel), aber ein Grund, den Serverzugang streng zu schuetzen.
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from datetime import datetime, timezone

import app.main  # noqa: F401 (registriert alle Modelle an Base.metadata)
from app.auth import mfa_service
from app.auth.models import PasswortResetToken, User
from app.auth.security_service import invalidate_security_context
from app.core.audit_log import record as record_audit
from app.core.crypto import decrypt_field, lookup_hash
from app.core.rls_lookup import mandant_des_nutzers
from app.core.security import hash_password
from app.db import SessionLocal, set_rls_mandant

MIN_LAENGE = 12  # wie bei der Registrierung (RegisterRequest)
MAX_LAENGE = 256


class WiederherstellungsFehler(Exception):
    """Meldung fuer die Person am Terminal, kein Programmfehler."""


def wiederherstellen(db, *, email: str, neues_passwort: str, mfa_zuruecksetzen: bool = False) -> str:
    """Setzt das Konto zurueck und gibt eine kurze Erfolgsmeldung zurueck. Committet selbst."""
    if not (MIN_LAENGE <= len(neues_passwort) <= MAX_LAENGE):
        raise WiederherstellungsFehler(f"Das Passwort muss zwischen {MIN_LAENGE} und {MAX_LAENGE} Zeichen lang sein.")
    user = db.query(User).filter(User.email_lookup_hash == lookup_hash(email.strip())).first()
    if user is None or user.geloescht_am is not None:
        raise WiederherstellungsFehler("Zu dieser E-Mail-Adresse gibt es kein aktives Konto (mit --konten-auflisten nachsehen).")
    mandant_id = mandant_des_nutzers(db, user.id)
    if mandant_id is None:
        raise WiederherstellungsFehler("Das Konto gehört zu keiner Firma (keine Mitgliedschaft) und kann nicht zurückgesetzt werden.")
    set_rls_mandant(db, mandant_id)

    user.passwort_hash = hash_password(neues_passwort)
    user.passwort_geaendert_am = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.locked_until = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_erstellt_am = None
    if mfa_zuruecksetzen:
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.mfa_letzter_zeitschritt = None
        mfa_service.loesche_wiederherstellungscodes(db, user)
    db.query(PasswortResetToken).filter(PasswortResetToken.user_id == user.id).delete(synchronize_session=False)
    invalidate_security_context(db, user)
    record_audit(
        db, aktion="konto_wiederhergestellt_betreiber", mandant_id=mandant_id, user_id=user.id,
        kontext="passwort+mfa" if mfa_zuruecksetzen else "passwort",
    )
    db.commit()
    hinweis = "Zwei-Faktor-Anmeldung wurde abgeschaltet. Bei Rollen mit MFA-Pflicht (Standard: Owner) richtet das Konto sie beim nächsten Login neu ein." if mfa_zuruecksetzen else (
        "Die Zwei-Faktor-Anmeldung bleibt aktiv (falls eingerichtet); bei verlorenem Gerät --mfa-zuruecksetzen verwenden."
    )
    return f"Passwort gesetzt, alle Sitzungen widerrufen. {hinweis}"


def konten_auflisten(db) -> list[str]:
    zeilen = []
    for user in db.query(User).order_by(User.erstellt_am).all():
        status = "gelöscht" if user.geloescht_am is not None else ("MFA an" if user.mfa_enabled else "MFA aus")
        zeilen.append(f"{decrypt_field(user.email_encrypted)}  ({status})")
    return zeilen


def _passwort_abfragen() -> str:
    erstes = getpass.getpass("Neues Passwort: ")
    if erstes != getpass.getpass("Neues Passwort wiederholen: "):
        raise WiederherstellungsFehler("Die beiden Eingaben stimmen nicht überein.")
    return erstes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Konto auf dieser Bilantiq-Instanz wiederherstellen (nur für Betreiber).")
    parser.add_argument("--email", help="E-Mail-Adresse des Kontos")
    parser.add_argument("--konten-auflisten", action="store_true", help="E-Mail-Adressen aller Konten anzeigen")
    parser.add_argument("--zufallspasswort", action="store_true", help="Passwort erzeugen und einmal ausgeben")
    parser.add_argument("--mfa-zuruecksetzen", action="store_true", help="Zwei-Faktor-Anmeldung zusätzlich abschalten")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        if args.konten_auflisten:
            for zeile in konten_auflisten(db):
                print(zeile)
            return 0
        if not args.email:
            parser.error("--email ist erforderlich (oder --konten-auflisten).")
        passwort = secrets.token_urlsafe(18) if args.zufallspasswort else _passwort_abfragen()
        meldung = wiederherstellen(db, email=args.email, neues_passwort=passwort, mfa_zuruecksetzen=args.mfa_zuruecksetzen)
        print(meldung)
        if args.zufallspasswort:
            print(f"Neues Passwort (nur jetzt sichtbar, danach ändern lassen): {passwort}")
        return 0
    except WiederherstellungsFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
