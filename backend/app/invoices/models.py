import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Kontakt(Base):
    __tablename__ = "kontakte"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    name: Mapped[str] = mapped_column(EncryptedText("kontakt.name"))
    strasse: Mapped[str | None] = mapped_column(EncryptedText("kontakt.strasse"), nullable=True)
    plz: Mapped[str | None] = mapped_column(EncryptedText("kontakt.plz"), nullable=True)
    ort: Mapped[str | None] = mapped_column(EncryptedText("kontakt.ort"), nullable=True)
    land: Mapped[str] = mapped_column(EncryptedText("kontakt.land"), default="DE")  # ISO 3166-1 alpha-2
    ust_id: Mapped[str | None] = mapped_column(EncryptedText("kontakt.ust_id"), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText("kontakt.email"), nullable=True)
    ist_geschaeftskunde: Mapped[bool] = mapped_column(Boolean, default=True)
    # Freitext, keine automatische Vergabe -- siehe Rechnungs-Designer-Toggle
    # "zeige_kundennummer" in app/auth/models.py::Mandant.
    kundennummer: Mapped[str | None] = mapped_column(EncryptedText("kontakt.kundennummer"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    typ: Mapped[str] = mapped_column(String(10), default="kunde")  # kunde | lieferant | beide
    anrede: Mapped[str | None] = mapped_column(EncryptedText("kontakt.anrede"), nullable=True)
    vorname: Mapped[str | None] = mapped_column(EncryptedText("kontakt.vorname"), nullable=True)
    nachname: Mapped[str | None] = mapped_column(EncryptedText("kontakt.nachname"), nullable=True)
    telefon: Mapped[str | None] = mapped_column(EncryptedText("kontakt.telefon"), nullable=True)
    notiz: Mapped[str | None] = mapped_column(EncryptedText("kontakt.notiz"), nullable=True)
    steuernummer: Mapped[str | None] = mapped_column(EncryptedText("kontakt.steuernummer"), nullable=True)
    iban: Mapped[str | None] = mapped_column(EncryptedText("kontakt.iban"), nullable=True)
    # Blind-Index der IBAN, damit der Bankabgleich die Gegenpartei ohne Entschluesseln findet.
    iban_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    bic: Mapped[str | None] = mapped_column(EncryptedText("kontakt.bic"), nullable=True)
    # None heisst: Standard aus den Buchhaltungseinstellungen.
    zahlungsziel_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    skonto_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Kaeuferreferenz fuer XRechnung an oeffentliche Auftraggeber (BT-10).
    leitweg_id: Mapped[str | None] = mapped_column(EncryptedText("kontakt.leitweg_id"), nullable=True)
    # Archivieren statt Loeschen: verwendete Kontakte bleiben fuer Rechnungen erhalten.
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Gesetzt, wenn der Kontakt aus einem Stammdaten-Import stammt (fuer "Import rueckgaengig").
    import_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("datenimporte.id"), index=True, nullable=True)


class Rechnungsnummernkreis(Base):
    """One counter row per (mandant, jahr). allocate_next() in numbering.py increments it
    inside the same transaction as the invoice finalization, so numbers stay gapless."""

    __tablename__ = "rechnungsnummernkreise"
    # Wie in Migration 0003: zwei Zaehler fuer dieselbe (Mandant, Jahr) wuerden doppelte Rechnungsnummern erlauben.
    __table_args__ = (UniqueConstraint("mandant_id", "jahr", name="uq_nummernkreis_mandant_jahr"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    jahr: Mapped[int] = mapped_column(Integer)
    naechste_nummer: Mapped[int] = mapped_column(Integer, default=1)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"))
    nummer: Mapped[str | None] = mapped_column(String(40), nullable=True)  # set on finalize only
    status: Mapped[str] = mapped_column(String(20), default="entwurf")  # entwurf | final | storniert
    leistungsdatum: Mapped[date] = mapped_column(Date)
    faelligkeitsdatum: Mapped[date] = mapped_column(Date)
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    netto_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("invoice.netto_gesamt"), default=Decimal("0"))
    ust_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("invoice.ust_gesamt"), default=Decimal("0"))
    brutto_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("invoice.brutto_gesamt"), default=Decimal("0"))
    e_invoice_format: Mapped[str | None] = mapped_column(String(20), nullable=True)  # xrechnung | zugferd
    korrigiert_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finalisiert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Manual for now — there is no bank feed yet (finAPI-style connection intentionally
    # deferred), so a human marks an invoice paid. See app/invoices/routes.py.
    bezahlt_am: Mapped[date | None] = mapped_column(Date, nullable=True)
    # E-Mail-Versand (app/core/mailer.py) -- unabhaengig vom Finalisieren (finalisiert_am
    # oben). Ein erneuter Versand ueberschreibt den Zeitstempel, es gibt keine Historie
    # mehrfacher Sendungen (siehe app/invoices/routes.py::send_invoice_email).
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Editor-Zusatzfelder (siehe frontend/src/features/invoices/InvoiceEditor.tsx).
    # betreff/fusstext wirken sich auf das PDF aus (Titel-/Fusszeilen-Override in
    # app/core/document_pdf.py — render_invoice_pdf loest [%ZAHLUNGSZIEL%]/
    # [%KONTAKTPERSON%] darin auf). kopftext/referenznummer/kostenstelle/
    # zahlungsmethode/skonto_*/interne_kontaktperson sind bewusst nur gespeicherte
    # Metadaten in dieser Runde, noch nicht im PDF platziert — siehe Docstring dort.
    betreff: Mapped[str | None] = mapped_column(EncryptedText("invoice.betreff"), nullable=True)
    kopftext: Mapped[str | None] = mapped_column(EncryptedText("invoice.kopftext"), nullable=True)
    fusstext: Mapped[str | None] = mapped_column(EncryptedText("invoice.fusstext"), nullable=True)
    referenznummer: Mapped[str | None] = mapped_column(EncryptedText("invoice.referenznummer"), nullable=True)
    kostenstelle: Mapped[str | None] = mapped_column(EncryptedText("invoice.kostenstelle"), nullable=True)
    zahlungsmethode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    skonto_tage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skonto_prozent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    interne_kontaktperson_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    kontakt: Mapped["Kontakt"] = relationship()
    interne_kontaktperson: Mapped["User | None"] = relationship()  # noqa: F821 (User lebt in app.auth.models)
    positionen: Mapped[list["InvoicePosition"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoicePosition.reihenfolge"
    )


class InvoicePosition(Base):
    __tablename__ = "invoice_positionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, default=0)
    beschreibung: Mapped[str] = mapped_column(EncryptedText("invoice_position.beschreibung"))
    menge: Mapped[Decimal] = mapped_column(EncryptedDecimal("invoice_position.menge"))
    einzelpreis: Mapped[Decimal] = mapped_column(EncryptedDecimal("invoice_position.einzelpreis"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # e.g. 19.00 / 7.00 / 0.00
    # Freitext, keine FK auf Positionskategorie -- eine spaeter umbenannte/geloeschte
    # Kategorie darf den historischen Text auf dieser Position nie veraendern (gleiche
    # Haltung wie bei allen anderen Positionsfeldern hier).
    kategorie: Mapped[str | None] = mapped_column(EncryptedText("invoice_position.kategorie"), nullable=True)
    artikelnummer: Mapped[str | None] = mapped_column(EncryptedText("invoice_position.artikelnummer"), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="positionen")


class Positionskategorie(Base):
    """Wiederverwendbare Vorschlagsliste fuer InvoicePosition.kategorie -- Werte kommen
    automatisch hinzu, sobald eine Rechnung mit einer neuen Kategorie angelegt/
    aktualisiert wird (siehe app/invoices/routes.py::_upsert_kategorien), nicht nur
    ueber eine eigene Verwaltungsseite."""

    __tablename__ = "positionskategorien"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    name: Mapped[str] = mapped_column(EncryptedText("positionskategorie.name"))
