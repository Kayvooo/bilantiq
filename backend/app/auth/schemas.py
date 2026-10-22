from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Muss synchron bleiben mit app/core/document_pdf.py::GUELTIGE_VORLAGEN und dem
# `vorlage`-Feld von RechnungsvorlageVorschauRequest (unten).
RECHNUNGSVORLAGEN = Literal[
    "klassisch", "modern", "minimal", "kompakt", "elegant", "balken",
    "seitenleiste", "rahmen", "kachel", "mono", "stempel",
]
DESIGN_VARIANTEN = Literal["standard", "schwarz", "blau", "einfach"]
LOGO_GROESSEN = Literal["S", "M", "L"]
SPRACHEN = Literal["de", "en"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)  # Obergrenze: Argon2 auf Megabyte-Eingaben waere ein DoS-Hebel
    # Nur Pflicht ohne Einladungscode -- wer einer bestehenden Firma beitritt, legt
    # keine neue an. Siehe register() in routes.py fuer die eigentliche Pruefung.
    firmenname: str | None = Field(default=None, max_length=255)
    einladungscode: str | None = Field(default=None, max_length=32)


class PreAuthResponse(BaseModel):
    # "mfa_optional": ohne MFA angemeldet, access_token gesetzt | "mfa_required": Code erforderlich |
    # "mfa_einrichtung_erforderlich": MFA ist Pflicht und noch nicht eingerichtet, nur pre_auth_token (docs/specs/mfa-pflicht.md)
    status: str
    pre_auth_token: str
    access_token: str | None = None


class BestaetigungRequest(BaseModel):
    """Frische MFA-Bestaetigung fuer eine sensible Aktion (docs/specs/mfa-pflicht.md). ``code``: TOTP-Code oder Wiederherstellungscode."""

    aktion: Literal["iban_aendern", "benutzer_verwalten", "gesamtexport"]
    code: str = Field(min_length=6, max_length=32)


class BestaetigungResponse(BaseModel):
    bestaetigung_token: str
    gueltig_bis: datetime


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    # "Dieses Geraet fuer 30 Tage merken" -- verlaengert nur die Gueltigkeit des
    # ausgestellten Tokens (siehe settings.remember_device_days), kein eigenes
    # Geraete-/Refresh-Token-Konzept.
    remember_device: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MfaAktiviertResponse(TokenResponse):
    """Antwort von /auth/mfa/verify. ``wiederherstellungscodes`` steht nur bei der ERSTEN Aktivierung drin und wird nie
    wieder angezeigt (in der Datenbank liegen nur Hashes)."""

    wiederherstellungscodes: list[str] | None = None


class WiederherstellungscodeLoginRequest(BaseModel):
    wiederherstellungscode: str = Field(min_length=8, max_length=32)
    remember_device: bool = False


class PasswortVergessenRequest(BaseModel):
    email: EmailStr


class PasswortVergessenResponse(BaseModel):
    detail: str


class PasswortZuruecksetzenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    neues_passwort: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class KontoLoeschenRequest(BaseModel):
    """Bestaetigung fuer DELETE /auth/me: aktuelles Passwort und, falls MFA aktiv ist, der aktuelle Code."""

    passwort: str = Field(max_length=256)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")


class MeResponse(BaseModel):
    user_id: str
    mandant_id: str
    firmenname: str
    rolle: str


class MandantUpdate(BaseModel):
    firmenname: str | None = Field(default=None, min_length=1, max_length=255)
    ust_id: str | None = None
    steuernummer: str | None = None
    adresse: str | None = None
    datev_beraternummer: str | None = None
    datev_mandantennummer: str | None = None
    steuerberater_name: str | None = None
    steuerberater_email: str | None = None
    steuerberater_telefon: str | None = None
    rechnungsvorlage: RECHNUNGSVORLAGEN | None = None
    akzentfarbe: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    fusszeile_text: str | None = Field(default=None, max_length=2000)
    design_variante: DESIGN_VARIANTEN | None = None
    logo_groesse: LOGO_GROESSEN | None = None
    briefpapier_id: str | None = None
    sprache: SPRACHEN | None = None
    iban: str | None = Field(default=None, max_length=34)
    bic: str | None = Field(default=None, max_length=11)
    telefon: str | None = Field(default=None, max_length=50)
    kontakt_email: str | None = Field(default=None, max_length=254)
    zeige_absenderzeile: bool | None = None
    zeige_kundennummer: bool | None = None
    zeige_kontaktperson: bool | None = None
    zeige_artikelnummer: bool | None = None
    zeige_positionsbeschreibung: bool | None = None
    zeige_ust_pro_position: bool | None = None
    zeige_girocode: bool | None = None
    zeige_fusszeile: bool | None = None
    zeige_seitenzahlen: bool | None = None
    zeige_falz_lochmarken: bool | None = None


class RechnungsvorlageVorschauRequest(BaseModel):
    """Ungespeicherte Design-Auswahl fuer die Vorschau (POST statt GET).

    Als Body statt Query-Parameter, weil IBAN/BIC/Fusszeile sonst im Zugriffslog landen wuerden.
    ``briefpapier_id``: Feld weglassen = gespeicherte Auswahl; null oder "" = kein Briefpapier."""

    vorlage: RECHNUNGSVORLAGEN | None = None
    akzentfarbe: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    fusszeile_text: str | None = Field(default=None, max_length=2000)
    design_variante: DESIGN_VARIANTEN | None = None
    logo_groesse: LOGO_GROESSEN | None = None
    sprache: SPRACHEN | None = None
    briefpapier_id: str | None = None
    iban: str | None = Field(default=None, max_length=34)
    bic: str | None = Field(default=None, max_length=11)
    zeige_absenderzeile: bool | None = None
    zeige_kundennummer: bool | None = None
    zeige_kontaktperson: bool | None = None
    zeige_artikelnummer: bool | None = None
    zeige_positionsbeschreibung: bool | None = None
    zeige_ust_pro_position: bool | None = None
    zeige_girocode: bool | None = None
    zeige_fusszeile: bool | None = None
    zeige_seitenzahlen: bool | None = None
    zeige_falz_lochmarken: bool | None = None


class MandantResponse(BaseModel):
    id: str
    firmenname: str
    ust_id: str | None
    steuernummer: str | None
    adresse: str | None
    datev_beraternummer: str | None
    datev_mandantennummer: str | None
    steuerberater_name: str | None
    steuerberater_email: str | None
    steuerberater_telefon: str | None
    rechnungsvorlage: str | None
    akzentfarbe: str | None
    fusszeile_text: str | None
    hat_logo: bool
    design_variante: str | None
    logo_groesse: str | None
    briefpapier_id: str | None
    sprache: str | None
    iban: str | None
    bic: str | None
    telefon: str | None
    kontakt_email: str | None
    zeige_absenderzeile: bool
    zeige_kundennummer: bool
    zeige_kontaktperson: bool
    zeige_artikelnummer: bool
    zeige_positionsbeschreibung: bool
    zeige_ust_pro_position: bool
    zeige_girocode: bool
    zeige_fusszeile: bool
    zeige_seitenzahlen: bool
    zeige_falz_lochmarken: bool


class BriefpapierResponse(BaseModel):
    id: str
    name: str


class EinladungCreate(BaseModel):
    rolle: str = Field(default="mitglied", pattern="^(mitglied|owner)$")


class EinladungResponse(BaseModel):
    id: str
    code: str
    rolle: str
    ablauf_am: str
    eingeloest_am: str | None
    widerrufen: bool


class MitgliedResponse(BaseModel):
    user_id: str
    email: str
    rolle: str


class MitgliedCreate(BaseModel):
    email: EmailStr
    rolle: str = Field(default="mitglied", pattern="^(mitglied|owner)$")


class MitgliedCreateResponse(BaseModel):
    user_id: str
    email: str
    rolle: str
    # Nur in dieser einen Antwort enthalten -- danach nirgends mehr abrufbar (kein
    # SMTP-Versand im Projekt, siehe Einladung-Docstring in app/auth/models.py).
    initial_passwort: str


class PasswortAendernRequest(BaseModel):
    aktuelles_passwort: str = Field(max_length=256)
    neues_passwort: str = Field(min_length=12, max_length=256)
