import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # TEXT statt String(1200): Migration 0036 hat die Chiffretexte physisch auf TEXT umgestellt.
    email_encrypted: Mapped[str] = mapped_column(Text)
    email_lookup_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    passwort_hash: Mapped[str] = mapped_column(String(255))
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending_erstellt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Replay-Schutz: letzter verbrauchter TOTP-Zeitschritt (Unix-Zeit // 30). Ein Code gilt nur, wenn sein Zeitschritt
    # groesser ist; siehe app/auth/mfa_service.py.
    mfa_letzter_zeitschritt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    security_version: Mapped[int] = mapped_column(Integer, default=1)
    passwort_geaendert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_geaendert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    geloescht_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mitgliedschaften: Mapped[list["Mitgliedschaft"]] = relationship(back_populates="user")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    user_agent: Mapped[str | None] = mapped_column(EncryptedText("auth_session.user_agent"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    laeuft_ab_am: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    widerrufen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailAenderung(Base):
    __tablename__ = "email_aenderungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    neue_email: Mapped[str] = mapped_column(EncryptedText("email_change.new_email"))
    neue_email_lookup_hash: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    versuche: Mapped[int] = mapped_column(Integer, default=0)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MfaWiederherstellungscode(Base):
    """Einmalcode als Ersatz fuer den TOTP-Code. Nur der HMAC-Hash wird gespeichert, der Klartext wird genau einmal
    beim Erzeugen angezeigt (siehe app/auth/mfa_service.py)."""

    __tablename__ = "mfa_wiederherstellungscodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    verbraucht_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswortResetToken(Base):
    """Einmal-Token fuer "Passwort vergessen". Nur der HMAC-Hash wird gespeichert, der Token steht nur im Link der
    E-Mail (siehe app/auth/passwort_reset.py)."""

    __tablename__ = "passwort_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verbraucht_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Mandant(Base):
    __tablename__ = "mandanten"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    firmenname: Mapped[str] = mapped_column(EncryptedText("mandant.firmenname"))
    ust_id: Mapped[str | None] = mapped_column(EncryptedText("mandant.ust_id"), nullable=True)
    steuernummer: Mapped[str | None] = mapped_column(EncryptedText("mandant.steuernummer"), nullable=True)
    adresse: Mapped[str | None] = mapped_column(EncryptedText("mandant.adresse"), nullable=True)
    # DATEV-assigned numbers for the Steuerberater relationship — Bilantiq cannot know
    # these, they come from the Kanzlei. See app/reports/datev.py.
    datev_beraternummer: Mapped[str | None] = mapped_column(EncryptedText("mandant.datev_beraternummer"), nullable=True)
    datev_mandantennummer: Mapped[str | None] = mapped_column(EncryptedText("mandant.datev_mandantennummer"), nullable=True)
    # Reine Kontaktdaten fuer "Mein Steuerberater" (frontend/src/features/auth/
    # SteuerberaterPage.tsx) -- keine eigene Rolle/kein eigener Zugang, nur damit
    # die Person schnell greifbar ist, wenn eine Auswertung geteilt werden soll.
    steuerberater_name: Mapped[str | None] = mapped_column(EncryptedText("mandant.steuerberater_name"), nullable=True)
    steuerberater_email: Mapped[str | None] = mapped_column(EncryptedText("mandant.steuerberater_email"), nullable=True)
    steuerberater_telefon: Mapped[str | None] = mapped_column(EncryptedText("mandant.steuerberater_telefon"), nullable=True)
    # Rechnungsvorlage/-farbe fuer alle PDF-Dokumente (Rechnung, Angebot,
    # Auftragsbestaetigung, Lieferschein) — siehe app/core/document_pdf.py.
    # rechnungsvorlage ist nullable statt einem DB-Default, damit "kein eigener Wert
    # gesetzt" (-> Default "klassisch" in document_pdf.py) sauber von "klassisch aktiv
    # gewaehlt" unterscheidbar bliebe, falls das je relevant wird.
    rechnungsvorlage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    akzentfarbe: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Logo als Datei ueber app/core/branding_storage.py (gleiches Muster wie
    # app/receipts/storage.py) — hier nur der relative Pfad, nicht die Bytes.
    logo_referenz: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fusszeile_text: Mapped[str | None] = mapped_column(EncryptedText("mandant.fusszeile_text"), nullable=True)
    # Rechnungs-Designer (siehe app/core/document_pdf.py) -- zweite Design-Achse
    # zusaetzlich zur Vorlage/Akzentfarbe, Logo-Groesse, Briefpapier, Sprache und
    # die Element-Toggles. Alles nullable statt DB-Default aus demselben Grund wie
    # rechnungsvorlage oben: "nichts gewaehlt" bleibt von "Standard aktiv gewaehlt"
    # unterscheidbar, auch wenn beides aktuell gleich gerendert wird.
    design_variante: Mapped[str | None] = mapped_column(String(20), nullable=True)
    logo_groesse: Mapped[str | None] = mapped_column(String(1), nullable=True)  # S | M | L
    # Kein FK auf briefpapiere.id hier auf Zweck -- Briefpapier.mandant_id zeigt schon
    # in die andere Richtung, ein FK auf beiden Seiten waere ein Abhaengigkeitszyklus
    # (bricht SQLites drop_all-Tabellensortierung, gleiches Muster wie
    # app/receipts/models.py::Ausgabe.receipt_id).
    briefpapier_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sprache: Mapped[str | None] = mapped_column(String(2), nullable=True)  # de | en
    # Fuer den GiroCode (EPC-QR) -- ohne IBAN wird kein QR gezeichnet, auch wenn
    # zeige_girocode aktiv ist. Keine Pruefsummen-Validierung, bewusst einfach.
    iban: Mapped[str | None] = mapped_column(EncryptedText("mandant.iban"), nullable=True)
    bic: Mapped[str | None] = mapped_column(EncryptedText("mandant.bic"), nullable=True)
    # Ansprechpartner-Daten des Verkaeufers: Pflicht in der XRechnung (BG-6 / BR-DE-2, -5, -7), sonst nirgends gebraucht.
    telefon: Mapped[str | None] = mapped_column(EncryptedText("mandant.telefon"), nullable=True)
    kontakt_email: Mapped[str | None] = mapped_column(EncryptedText("mandant.kontakt_email"), nullable=True)
    # Element-Toggles fuers PDF. Defaults entsprechen dem Verhalten vor dieser
    # Migration (keine Regression fuer bestehende Rechnungen): Absenderzeile/
    # Positionsbeschreibung/USt-pro-Position/Fusszeile waren immer an, Kundennummer/
    # Kontaktperson/Artikelnummer/GiroCode/Seitenzahlen/Falz-Lochmarken gab es noch
    # gar nicht (also aus).
    zeige_absenderzeile: Mapped[bool] = mapped_column(Boolean, default=True)
    zeige_kundennummer: Mapped[bool] = mapped_column(Boolean, default=False)
    zeige_kontaktperson: Mapped[bool] = mapped_column(Boolean, default=False)
    zeige_artikelnummer: Mapped[bool] = mapped_column(Boolean, default=False)
    zeige_positionsbeschreibung: Mapped[bool] = mapped_column(Boolean, default=True)
    zeige_ust_pro_position: Mapped[bool] = mapped_column(Boolean, default=True)
    zeige_girocode: Mapped[bool] = mapped_column(Boolean, default=False)
    zeige_fusszeile: Mapped[bool] = mapped_column(Boolean, default=True)
    zeige_seitenzahlen: Mapped[bool] = mapped_column(Boolean, default=False)
    zeige_falz_lochmarken: Mapped[bool] = mapped_column(Boolean, default=False)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    mitgliedschaften: Mapped[list["Mitgliedschaft"]] = relationship(back_populates="mandant")
    # primaryjoin statt ForeignKey (siehe briefpapier_id oben) -- SQLAlchemy kann die
    # Join-Bedingung ohne echten FK nicht selbst ableiten, deshalb explizit mit
    # foreign() markiert, welche Seite die "fremde" ist.
    briefpapier: Mapped["Briefpapier | None"] = relationship(
        primaryjoin="foreign(Mandant.briefpapier_id) == Briefpapier.id",
    )


class Briefpapier(Base):
    """Vom Mandanten hochgeladenes Hintergrundbild (z.B. vorgedrucktes Geschaeftspapier-
    Design), waehlbar im Rechnungs-Designer. Datei liegt ueber
    app/core/letterhead_storage.py, gleiches Muster wie Logo/Belege."""

    __tablename__ = "briefpapiere"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    name: Mapped[str] = mapped_column(EncryptedText("briefpapier.name"))
    datei_referenz: Mapped[str] = mapped_column(String(500))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Mitgliedschaft(Base):
    __tablename__ = "mitgliedschaften"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    rolle: Mapped[str] = mapped_column(String(20), default="owner")  # owner | mitglied

    user: Mapped["User"] = relationship(back_populates="mitgliedschaften")
    mandant: Mapped["Mandant"] = relationship(back_populates="mitgliedschaften")


class Einladung(Base):
    """Einladungscode statt E-Mail-Versand — es gibt keine SMTP-Anbindung in diesem
    Projekt. Der Owner gibt den Code manuell weiter (beliebiger Kanal), die
    eingeladene Person registriert sich damit unter app.auth.routes.register()
    gegen den bestehenden Mandanten statt einen neuen anzulegen."""

    __tablename__ = "einladungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    rolle: Mapped[str] = mapped_column(String(20), default="mitglied")
    erstellt_von: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    eingeloest_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    widerrufen: Mapped[bool] = mapped_column(Boolean, default=False)
