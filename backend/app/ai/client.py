import json
from typing import TypeVar

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)


class AiUnavailable(RuntimeError):
    pass


class AiResponseError(RuntimeError):
    pass


class AiClient:
    """Kleiner OpenAI-kompatibler Client fuer einen lokalen Inference-Service.

    Bewusst kein Cloud-Fallback: ist der konfigurierte interne Dienst nicht erreichbar,
    scheitert die KI-Funktion klar, waehrend die restliche Buchhaltung weiterlaeuft.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    def _complete(self, messages: list[dict[str, str]], *, temperature: float = 0.1) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AiUnavailable("Lokaler KI-Dienst ist nicht erreichbar.") from exc

        if response.status_code >= 500:
            raise AiUnavailable("Lokaler KI-Dienst ist voruebergehend nicht verfuegbar.")
        if response.status_code >= 400:
            raise AiResponseError(f"Lokaler KI-Dienst hat HTTP {response.status_code} geliefert.")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AiResponseError("Lokaler KI-Dienst hat kein gueltiges Chat-Ergebnis geliefert.") from exc
        if not isinstance(content, str) or not content.strip():
            raise AiResponseError("Lokaler KI-Dienst hat eine leere Antwort geliefert.")
        return content.strip()

    def complete_text(self, messages: list[dict[str, str]]) -> str:
        return self._complete(messages)

    def complete_json(self, messages: list[dict[str, str]], schema: type[T]) -> T:
        content = self._complete(messages)
        # Viele lokale OpenAI-kompatible Server unterstuetzen response_format noch
        # unterschiedlich. Deshalb erzwingt der Prompt JSON und der Client extrahiert
        # robust das erste JSON-Objekt, statt provider-spezifische Features zu verlangen.
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end < start:
            raise AiResponseError("KI-Antwort enthaelt kein JSON-Objekt.")
        try:
            raw = json.loads(content[start : end + 1])
            return schema.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AiResponseError("KI-Antwort entspricht nicht dem erwarteten Schema.") from exc


def get_ai_client() -> AiClient:
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lokale KI ist in dieser Installation nicht aktiviert.",
        )
    return AiClient(
        base_url=settings.ai_base_url,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        api_key=settings.ai_api_key,
    )
