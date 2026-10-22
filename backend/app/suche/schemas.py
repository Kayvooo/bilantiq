from pydantic import BaseModel, Field, field_validator

from app.suche.service import MIN_ZEICHEN


class SucheAnfrage(BaseModel):
    q: str = Field(max_length=100)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("q")
    @classmethod
    def _mindestlaenge(cls, wert: str) -> str:
        wert = wert.strip()
        if len(wert) < MIN_ZEICHEN:
            raise ValueError(f"Bitte mindestens {MIN_ZEICHEN} Zeichen eingeben.")
        return wert


class TrefferResponse(BaseModel):
    id: str
    titel: str
    untertitel: str | None
    ziel: str  # Name der Seite im Frontend (DesktopStep)


class GruppeResponse(BaseModel):
    typ: str
    label: str
    treffer: list[TrefferResponse]
    gesamt: int  # alle Treffer dieses Typs, nicht nur die gezeigten


class SucheResponse(BaseModel):
    gruppen: list[GruppeResponse]
    unvollstaendig: list[str]  # Typen, bei denen nicht alle Daten durchsucht wurden
