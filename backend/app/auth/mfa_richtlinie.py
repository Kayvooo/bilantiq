"""Welche Rollen MFA brauchen (MFA_PFLICHT, siehe docs/specs/mfa-pflicht.md).

Die Rolle kommt immer aus der aktuellen Mitgliedschaft in der Datenbank, nie aus dem Token: Ein Rollenwechsel oder eine
geaenderte Richtlinie wirkt damit sofort auf bestehende Sitzungen."""
from __future__ import annotations

from app.config import settings


def mfa_erforderlich(rolle: str | None) -> bool:
    """True, wenn ein Konto mit dieser Mandantenrolle MFA eingerichtet haben muss."""
    if settings.mfa_pflicht == "aus":
        return False
    if settings.mfa_pflicht == "alle":
        return True
    return rolle == "owner"


MFA_EINRICHTUNG_ERFORDERLICH = "Zwei-Faktor-Anmeldung muss eingerichtet werden. Bitte melde dich neu an."
