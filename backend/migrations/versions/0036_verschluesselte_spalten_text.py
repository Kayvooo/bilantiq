"""Verschlüsselte Spalten physisch auf TEXT umstellen und Klartext nachverschlüsseln.

Die Modelle nutzen EncryptedText/EncryptedDecimal (Chiffrat als Text), die Spalten
waren aber noch NUMERIC/VARCHAR(n) aus den ersten Migrationen. Migration 0029 hat nur
eine handgepflegte Liste umgestellt. Auf SQLite fällt das nicht auf, auf Postgres
scheitert jeder Schreibvorgang. Vorhandene Klartextwerte werden mit dem
Spalten-Zweck (purpose) verschlüsselt, schon verschlüsselte bleiben unberührt.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

from app.core.key_management import encrypt_text, is_encrypted_text


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


_SPALTEN: dict[str, dict[str, str]] = {
    "anlagen": {
        "anschaffungskosten_netto": "anlage.anschaffungskosten_netto",  # Dezimalzahl
    },
    "auftragsbestaetigung_positionen": {
        "menge": "auftrag_position.menge",  # Dezimalzahl
        "einzelpreis": "auftrag_position.einzelpreis",  # Dezimalzahl
    },
    "auftragsbestaetigungen": {
        "netto_gesamt": "auftrag.netto_gesamt",  # Dezimalzahl
        "ust_gesamt": "auftrag.ust_gesamt",  # Dezimalzahl
        "brutto_gesamt": "auftrag.brutto_gesamt",  # Dezimalzahl
    },
    "ausgabe_steueranteile": {
        "bruttobetrag": "ausgabe_steueranteil.bruttobetrag",  # Dezimalzahl
    },
    "ausgaben": {
        "betrag": "ausgabe.betrag",  # Dezimalzahl
        "kategorie": "ausgabe.kategorie",
    },
    "invoice_positionen": {
        "menge": "invoice_position.menge",  # Dezimalzahl
        "einzelpreis": "invoice_position.einzelpreis",  # Dezimalzahl
        "kategorie": "invoice_position.kategorie",
        "artikelnummer": "invoice_position.artikelnummer",
    },
    "invoices": {
        "netto_gesamt": "invoice.netto_gesamt",  # Dezimalzahl
        "ust_gesamt": "invoice.ust_gesamt",  # Dezimalzahl
        "brutto_gesamt": "invoice.brutto_gesamt",  # Dezimalzahl
    },
    "kassenbuch_eintraege": {
        "betrag": "kassenbuch.betrag",  # Dezimalzahl
    },
    "kontakte": {
        "land": "kontakt.land",
    },
    "lagerbewegungen": {
        "menge": "lagerbewegung.menge",  # Dezimalzahl
    },
    "lieferschein_positionen": {
        "menge": "auftrag_position.menge",  # Dezimalzahl
    },
    "lohn_monatsentwuerfe": {
        "grundbrutto": "payroll.grundbrutto",  # Dezimalzahl
        "steuerpflichtige_zuschlaege": "payroll.steuerpflichtige_zuschlaege",  # Dezimalzahl
        "steuerfreie_erstattungen": "payroll.steuerfreie_erstattungen",  # Dezimalzahl
        "sonstige_abzuege": "payroll.sonstige_abzuege",  # Dezimalzahl
        "gesamtbrutto": "payroll.gesamtbrutto",  # Dezimalzahl
        "zwischenbetrag_vor_abgaben": "payroll.zwischenbetrag_vor_abgaben",  # Dezimalzahl
    },
    "mitarbeitende": {
        "monatsbrutto": "payroll.monatsbrutto",  # Dezimalzahl
    },
    "positionskategorien": {
        "name": "positionskategorie.name",
    },
    "produkte": {
        "einzelpreis": "produkt.einzelpreis",  # Dezimalzahl
        "einheit": "produkt.einheit",
    },
    "quote_positionen": {
        "menge": "quote_position.menge",  # Dezimalzahl
        "einzelpreis": "quote_position.einzelpreis",  # Dezimalzahl
    },
    "quotes": {
        "netto_gesamt": "quote.netto_gesamt",  # Dezimalzahl
        "ust_gesamt": "quote.ust_gesamt",  # Dezimalzahl
        "brutto_gesamt": "quote.brutto_gesamt",  # Dezimalzahl
    },
    "receipts": {
        "betrag": "receipt.betrag",  # Dezimalzahl
        "kategorie_vorschlag": "receipt.kategorie_vorschlag",
    },
    "sonstige_einnahmen": {
        "betrag_brutto": "einnahme.betrag_brutto",  # Dezimalzahl
    },
    "wiederkehrende_ausgaben": {
        "betrag": "wiederkehrende_ausgabe.betrag",  # Dezimalzahl
        "kategorie": "wiederkehrende_ausgabe.kategorie",
    },
    "wiederkehrende_rechnung_positionen": {
        "menge": "wiederkehrend_position.menge",  # Dezimalzahl
        "einzelpreis": "wiederkehrend_position.einzelpreis",  # Dezimalzahl
    },
}

def _auf_text_umstellen() -> None:
    bind = op.get_bind()
    for tabelle, spalten in _SPALTEN.items():
        if bind.dialect.name == "postgresql":
            for spalte in spalten:
                op.execute(f'ALTER TABLE "{tabelle}" ALTER COLUMN "{spalte}" TYPE TEXT USING "{spalte}"::text')
        else:
            with op.batch_alter_table(tabelle) as batch:
                for spalte in spalten:
                    batch.alter_column(spalte, type_=sa.Text())


def _klartext_verschluesseln() -> None:
    bind = op.get_bind()
    for tabelle, spalten in _SPALTEN.items():
        for spalte, purpose in spalten.items():
            zeilen = bind.execute(
                sa.text(f'SELECT id, "{spalte}" AS wert FROM "{tabelle}" WHERE "{spalte}" IS NOT NULL')
            ).mappings().all()
            for zeile in zeilen:
                wert = str(zeile["wert"])
                if is_encrypted_text(wert):
                    continue
                bind.execute(
                    sa.text(f'UPDATE "{tabelle}" SET "{spalte}" = :wert WHERE id = :id'),
                    {"wert": encrypt_text(wert, purpose=purpose), "id": zeile["id"]},
                )


def upgrade() -> None:
    _auf_text_umstellen()
    _klartext_verschluesseln()


def downgrade() -> None:
    raise NotImplementedError(
        "Nicht umkehrbar: Die Werte sind verschlüsselt. Rückweg nur über ein Backup."
    )
