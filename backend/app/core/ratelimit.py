"""Einfache serverseitige Begrenzung von Anfragen (Gleitfenster), ohne zusaetzliche Abhaengigkeit.

Gedacht gegen automatisiertes Durchprobieren (Login, Registrierung, Einladungscodes) und gegen
Mail-Missbrauch. Der Zustand liegt im Arbeitsspeicher des Prozesses:

- Das Produktions-Image startet genau einen uvicorn-Prozess; mit mehreren Workern wuerde jeder
  Prozess eigene Zaehler fuehren (die effektive Grenze wuerde mit der Workerzahl wachsen).
- Ein Neustart setzt die Zaehler zurueck. Konto-bezogene Sperren (Passwort, MFA-Code) liegen deshalb
  zusaetzlich dauerhaft in der Datenbank (``User.failed_login_count``/``locked_until``, siehe
  ``app/auth/bruteforce.py``).
- Die Client-IP kommt aus ``request.client`` (uvicorn ``--proxy-headers`` setzt sie aus dem
  ``X-Forwarded-For`` des vorgeschalteten Caddy).
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

_MAX_SCHLUESSEL = 50_000  # Schutz gegen unbegrenztes Wachstum des Speichers


class _Fenster:
    def __init__(self) -> None:
        self._ereignisse: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def zaehle(self, schluessel: str, limit: int, fenster_sekunden: float) -> float | None:
        """Registriert einen Versuch. Gibt None zurueck, wenn er erlaubt ist, sonst die Wartezeit in Sekunden."""
        jetzt = time.monotonic()
        with self._lock:
            if len(self._ereignisse) > _MAX_SCHLUESSEL:
                self._aufraeumen(jetzt)
            warteschlange = self._ereignisse.setdefault(schluessel, deque())
            while warteschlange and warteschlange[0] <= jetzt - fenster_sekunden:
                warteschlange.popleft()
            if len(warteschlange) >= limit:
                return max(1.0, warteschlange[0] + fenster_sekunden - jetzt)
            warteschlange.append(jetzt)
            return None

    def _aufraeumen(self, jetzt: float) -> None:
        # Eintraege, deren juengstes Ereignis laenger als eine Stunde zurueckliegt, sind in jedem Fenster abgelaufen.
        for schluessel in [k for k, q in self._ereignisse.items() if not q or q[-1] < jetzt - 3600]:
            del self._ereignisse[schluessel]

    def zuruecksetzen(self) -> None:
        with self._lock:
            self._ereignisse.clear()


_fenster = _Fenster()


def zuruecksetzen() -> None:
    """Nur fuer Tests: leert alle Zaehler."""
    _fenster.zuruecksetzen()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unbekannt"


def begrenze(schluessel: str, *, limit: int, fenster_sekunden: float) -> None:
    """Wirft 429 mit ``Retry-After``, wenn ``schluessel`` das Limit im Zeitfenster ueberschritten hat."""
    warten = _fenster.zaehle(schluessel, limit, fenster_sekunden)
    if warten is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Versuche. Bitte warte einen Moment und versuche es dann erneut.",
            headers={"Retry-After": str(int(warten) + 1)},
        )


def begrenze_ip(request: Request, aktion: str, *, limit: int, fenster_sekunden: float) -> None:
    begrenze(f"{aktion}:ip:{client_ip(request)}", limit=limit, fenster_sekunden=fenster_sekunden)
