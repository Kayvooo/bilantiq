"""Zeilensperren fuer Schreibvorgaenge, die pro Mandant bzw. Einladung serialisiert werden muessen.

PostgreSQL haelt die Zeilensperre bis zum Ende der laufenden Transaktion. SQLite ignoriert
``FOR UPDATE`` erwartungsgemaess, fuehrt dieselbe Statement-Struktur aber weiterhin aus.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Einladung, Mandant


def sperre_mandant(db: Session, mandant_id: str) -> Mandant | None:
    """Serialisiert gleichzeitige Schreibvorgaenge pro Mandant (z. B. Rechnungsnummern, Zahlungen)."""
    return db.scalar(select(Mandant).where(Mandant.id == mandant_id).with_for_update())


def sperre_einladung(db: Session, code: str) -> Einladung | None:
    """Sperrt einen Einladungscode fuer eine atomare, einmalige Einloesung."""
    return db.scalar(select(Einladung).where(Einladung.code == code).with_for_update())
