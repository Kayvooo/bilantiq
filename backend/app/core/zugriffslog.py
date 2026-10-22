"""Datensparsamer uvicorn-Zugriffslog: Query-Strings gehoeren nicht ins Log.

uvicorn schreibt pro Anfrage eine Zeile wie ``1.2.3.4:5 - "GET /invoices?suche=x HTTP/1.1" 200``.
Dort stehen Query-Strings, die nicht ins Log gehoeren: Sie koennen Such-/Filterbegriffe, Namen von Anbietern
u. ae. enthalten. Die Anwendung nutzt sie nur fuer Filter und Zeitraeume; fuer die Fehleranalyse genuegen
Methode, Pfad und Status. Der Query-String wird daher komplett durch ``?[gekuerzt]`` ersetzt.

Der Filter haengt am Logger ``uvicorn.access`` und aendert nur das Pfad-Argument des Log-Eintrags
(IP-Adresse, Methode, Statuscode bleiben fuer die Fehleranalyse erhalten). Er wird beim Import von
``app.main`` und im Lifespan installiert (idempotent); uvicorn richtet sein Logging vor dem Import der App ein.

Grenzen: Es werden nur Zugriffszeilen maskiert. Tracebacks von ``uvicorn.error`` und Meldungen anderer
Logger bleiben unveraendert; ein Reverse-Proxy mit eigenem Zugriffslog (Caddy ist so konfiguriert, dass er keines
fuehrt) muesste separat behandelt werden.
"""
from __future__ import annotations

import logging

ZUGRIFFSLOGGER = "uvicorn.access"
QUERY_PLATZHALTER = "?[gekuerzt]"


def maskiere_pfad(pfad: str) -> str:
    """Entfernt den Query-String aus dem Pfad."""
    pfad_ohne_query, trenner, _ = pfad.partition("?")
    return pfad_ohne_query + (QUERY_PLATZHALTER if trenner else "")


class ZugriffslogMaskierung(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn: (client_addr, method, full_path, http_version, status_code)
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (args[0], args[1], maskiere_pfad(args[2]), *args[3:])
        return True


def installiere_zugriffslog_maskierung() -> None:
    """Haengt den Filter an ``uvicorn.access`` (mehrfacher Aufruf fuegt ihn nicht doppelt ein)."""
    logger = logging.getLogger(ZUGRIFFSLOGGER)
    if not any(isinstance(f, ZugriffslogMaskierung) for f in logger.filters):
        logger.addFilter(ZugriffslogMaskierung())
