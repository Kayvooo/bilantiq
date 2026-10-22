from decimal import Decimal

from pydantic import BaseModel, Field


class BuchhaltungseinstellungenPayload(BaseModel):
    standard_zahlungsziel_tage: int = Field(ge=0, le=365)
    standard_ust_satz: Decimal = Field(ge=0, le=100)
    kleinunternehmer: bool


class BuchhaltungseinstellungenResponse(BuchhaltungseinstellungenPayload):
    pass
