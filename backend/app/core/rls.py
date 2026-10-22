"""Mandant isolation, enforced twice.

Production (Postgres): every mandant-scoped table has a row-level security policy
(see migrations/versions/0001_initial.py) that rejects rows outside the mandant bound
via `app.current_mandant_id` for the current transaction (set in app/db.py).

Everywhere (Postgres and the SQLite used for local dev/tests): every query for a
mandant-scoped model also filters explicitly by mandant_id here. RLS can fail silently
if a migration is missed on a new table; the explicit filter cannot forget the same way,
and it is the only isolation layer available under SQLite. Neither layer alone is enough.
"""

from fastapi import HTTPException, status
from sqlalchemy import Select
from sqlalchemy.orm import Session


class MandantMismatchError(Exception):
    """Raised when a record's mandant_id does not match the requesting user's mandant."""


def scoped(stmt: Select, model, mandant_id: str) -> Select:
    return stmt.where(model.mandant_id == mandant_id)


def assert_same_mandant(record_mandant_id: str, mandant_id: str) -> None:
    if record_mandant_id != mandant_id:
        raise MandantMismatchError(f"Zugriff auf fremden Mandanten verweigert: {record_mandant_id} != {mandant_id}")


def get_scoped_or_404(db: Session, model, record_id: str, mandant_id: str):
    obj = db.get(model, record_id)
    if obj is None or getattr(obj, "mandant_id", None) != mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden.")
    return obj
