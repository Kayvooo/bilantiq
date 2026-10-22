from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


AssistantTool = Literal[
    "dashboard",
    "euer",
    "ustva",
    "bwa",
    "susa",
    "cashflow",
    "offene_rechnungen",
    "ueberfaellige_rechnungen",
    "ausgaben",
    "ausgaben_nach_kategorie",
    "keine",
]


class AssistantRequest(BaseModel):
    frage: str = Field(min_length=2, max_length=2000)
    jahr: int | None = Field(default=None, ge=2000, le=2100)


class AssistantPlan(BaseModel):
    tool: AssistantTool
    jahr: int | None = Field(default=None, ge=2000, le=2100)
    zeitraum_typ: Literal["monat", "quartal"] | None = None
    periode: int | None = Field(default=None, ge=1, le=12)
    wochen: int | None = Field(default=None, ge=1, le=26)
    von: date | None = None
    bis: date | None = None


class AssistantResponse(BaseModel):
    antwort: str
    tool: AssistantTool


class NaturalLanguageDraftRequest(BaseModel):
    anweisung: str = Field(min_length=3, max_length=4000)


class TextSuggestionRequest(BaseModel):
    art: Literal["rechnung", "angebot", "mahnung"]
    objekt_id: str
    ton: Literal["freundlich", "neutral", "bestimmt"] = "neutral"
    hinweis: str | None = Field(default=None, max_length=1000)


class TextSuggestionResponse(BaseModel):
    text: str
