from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

IS_POSTGRES = engine.dialect.name == "postgresql"


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_MANDANT_SQL = text("SELECT set_config('app.current_mandant_id', :mandant_id, true)")


def set_rls_mandant(db: Session, mandant_id: str) -> None:
    """Bind the Session to one Mandant for Postgres row-level security.

    Every mandant-scoped table's RLS policy checks current_setting('app.current_mandant_id').
    On SQLite (local dev/tests) this is a no-op — isolation there relies on the explicit
    mandant_id filters in the query layer (see app/core/rls.py), which is why every
    mandant-scoped query must also filter explicitly and never rely on RLS alone in tests.

    set_config(..., true) gilt nur bis zum Ende der Transaktion (SET LOCAL kennt keine Bind-Parameter,
    psycopg meldet SQLSTATE 42601). Die Anwendung committet mehrmals pro Anfrage; deshalb merkt sich die
    Session den Mandanten und `_mandant_bei_transaktionsbeginn` setzt ihn bei jeder neuen Transaktion erneut.
    """
    if not IS_POSTGRES:
        return
    db.info["rls_mandant_id"] = mandant_id
    db.execute(_MANDANT_SQL, {"mandant_id": mandant_id})


@event.listens_for(Session, "after_begin")
def _mandant_bei_transaktionsbeginn(session: Session, transaction, connection) -> None:
    mandant_id = session.info.get("rls_mandant_id")
    if mandant_id is not None:
        connection.execute(_MANDANT_SQL, {"mandant_id": mandant_id})
