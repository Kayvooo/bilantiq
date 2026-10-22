"""Mandanten-ID finden, bevor ein Mandantenkontext besteht.

Unter Postgres ohne BYPASSRLS sehen Abfragen auf RLS-Tabellen ohne gesetzten Mandanten nichts.
Registrierung mit Einladungscode und Anmeldung kennen den Mandanten aber erst
nach dem Nachschlagen. Dafür gibt es die engen SECURITY-DEFINER-Funktionen aus Migration 0035;
unter SQLite (Entwicklung, Tests) genügt die normale Abfrage, dort gibt es keine RLS.
Nach dem Nachschlagen immer `set_rls_mandant` aufrufen, bevor weitere Zeilen gelesen werden.
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.models import Einladung, Mitgliedschaft
from app.db import IS_POSTGRES


def mandant_aus_einladung(db: Session, code: str) -> str | None:
    if IS_POSTGRES:
        return db.scalar(text("SELECT bq_mandant_aus_einladung(:wert)"), {"wert": code})
    return db.scalar(select(Einladung.mandant_id).where(Einladung.code == code))


def mandant_des_nutzers(db: Session, user_id: str) -> str | None:
    if IS_POSTGRES:
        return db.scalar(text("SELECT bq_mandant_des_nutzers(:wert)"), {"wert": user_id})
    return db.scalar(select(Mitgliedschaft.mandant_id).where(Mitgliedschaft.user_id == user_id).order_by(Mitgliedschaft.id).limit(1))
