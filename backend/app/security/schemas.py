from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class SessionResponse(BaseModel):
    id: str
    aktuell: bool
    user_agent: str | None
    erstellt_am: datetime
    laeuft_ab_am: datetime


class SecurityOverviewResponse(BaseModel):
    email: EmailStr
    mfa_enabled: bool
    # Anzahl noch unbenutzter Wiederherstellungscodes (None, solange MFA aus ist).
    wiederherstellungscodes_offen: int | None = None
    passwort_geaendert_am: datetime | None
    email_geaendert_am: datetime | None
    sessions: list[SessionResponse]


class EmailChangeStartRequest(BaseModel):
    neues_email: EmailStr
    aktuelles_passwort: str = Field(max_length=256)


class EmailChangeConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaResetStartRequest(BaseModel):
    aktuelles_passwort: str = Field(max_length=256)
    # 6-stelliger TOTP-Code ODER ein Wiederherstellungscode (Format XXXXX-XXXXX); die Unterscheidung trifft die Route.
    aktueller_code: str = Field(min_length=6, max_length=32)


class MfaResetStartResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaResetConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaBestaetigtResponse(BaseModel):
    # Nur bei der ersten Aktivierung gesetzt; wird nie wieder angezeigt.
    wiederherstellungscodes: list[str] | None = None


class WiederherstellungscodesResponse(BaseModel):
    wiederherstellungscodes: list[str]
