from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.auth.models import Briefpapier, Einladung, Mandant, Mitgliedschaft, User  # noqa: F401 (registers models on Base)
from app.buchhaltungseinstellungen.models import Buchhaltungseinstellungen  # noqa: F401
from app.core.audit_log import AuditLogEintrag  # noqa: F401
from app.einnahmen.models import SonstigeEinnahme  # noqa: F401
from app.invoices.models import (  # noqa: F401
    Invoice,
    InvoicePosition,
    Kontakt,
    Positionskategorie,
    Rechnungsnummernkreis,
)
from app.quotes.models import Angebotsnummernkreis, Quote, QuotePosition  # noqa: F401
from app.receipts.models import Ausgabe, Receipt  # noqa: F401
from app.mahnwesen.models import Mahnung  # noqa: F401
from app.payroll.models import LohnMonatsentwurf, Mitarbeiter  # noqa: F401
from app.wiederkehrend.models import (  # noqa: F401
    WiederkehrendeAusgabe,
    WiederkehrendeRechnung,
    WiederkehrendeRechnungPosition,
)
from app.kassenbuch.models import KassenbuchEintrag  # noqa: F401
from app.anlagen.models import Anlage  # noqa: F401
from app.produkte.models import Lagerbewegung, Produkt  # noqa: F401
from app.stammdaten.models import Datenimport  # noqa: F401
from app.altrechnungen.models import Altrechnung, AltrechnungZahlung  # noqa: F401
from app.auftraege.models import (  # noqa: F401
    Auftragsbestaetigung,
    AuftragsbestaetigungPosition,
    Auftragsbestaetigungsnummernkreis,
    Lieferschein,
    LieferscheinPosition,
    Lieferscheinnummernkreis,
)
from app.config import settings
from app.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
