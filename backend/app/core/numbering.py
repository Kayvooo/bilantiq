from sqlalchemy.orm import Session

from app.db import IS_POSTGRES


def allocate_gapless_number(db: Session, counter_model, *, mandant_id: str, jahr: int, prefix: str) -> str:
    """Shared by invoices and quotes numbering — gapless, per-mandant-per-year.

    `counter_model` is any model with (mandant_id, jahr, naechste_nummer) columns; each
    caller uses its own table (see app/invoices/numbering.py, app/quotes/numbering.py)
    so invoice and quote sequences never share a counter row.

    Must run inside the same commit as the state change that consumes the number
    (finalizing an invoice, sending a quote) — allocating a number and then failing to
    save would leave a gap, which GoBD forbids.

    with_for_update() row-locks the counter on Postgres so two concurrent callers can't
    read the same next number. SQLite has no such lock (fine for local dev/tests, which
    are single-threaded) — same "RLS is Postgres-only, filter everywhere" pattern as
    app/core/rls.py.
    """
    query = db.query(counter_model).filter_by(mandant_id=mandant_id, jahr=jahr)
    if IS_POSTGRES:
        query = query.with_for_update()
    counter = query.first()

    if counter is None:
        counter = counter_model(mandant_id=mandant_id, jahr=jahr, naechste_nummer=1)
        db.add(counter)
        db.flush()

    number = counter.naechste_nummer
    counter.naechste_nummer += 1
    return f"{prefix}-{jahr}-{number:04d}"
