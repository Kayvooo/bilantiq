"""Zugriffslog-Maskierung (Release-Haertung): Query-Strings duerfen nicht im uvicorn-Log stehen."""
import io
import logging

import pytest

from app.core.zugriffslog import (
    ZUGRIFFSLOGGER, ZugriffslogMaskierung, installiere_zugriffslog_maskierung, maskiere_pfad,
)


@pytest.mark.parametrize("roh,erwartet", [
    ("/belege/vorschlag?anbieter=Max+Mustermann", "/belege/vorschlag?[gekuerzt]"),
    ("/invoices/abc-123", "/invoices/abc-123"),
    ("/health", "/health"),
])
def test_maskiere_pfad(roh, erwartet):
    assert maskiere_pfad(roh) == erwartet


def test_uvicorn_zugriffszeile_wird_maskiert_und_behaelt_ip_methode_status():
    strom = io.StringIO()
    handler = logging.StreamHandler(strom)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(ZUGRIFFSLOGGER)
    installiere_zugriffslog_maskierung()
    # Andere Tests (Alembic-fileConfig) koennen bestehende Logger deaktivieren; hier gezielt wieder einschalten.
    alt_level, alt_handlers, alt_disabled = logger.level, logger.handlers[:], logger.disabled
    logger.handlers, logger.level, logger.disabled = [handler], logging.INFO, False
    try:
        # Format wie uvicorn: '%s - "%s %s HTTP/%s" %d'
        logger.info('%s - "%s %s HTTP/%s" %d', "203.0.113.7:5555", "GET", "/belege/vorschlag?iban=DE89", "1.1", 200)
    finally:
        logger.handlers, logger.level, logger.disabled = alt_handlers, alt_level, alt_disabled
    zeile = strom.getvalue()
    assert "DE89" not in zeile
    assert zeile.strip() == '203.0.113.7:5555 - "GET /belege/vorschlag?[gekuerzt] HTTP/1.1" 200'


def test_filter_wird_beim_app_import_installiert_und_nicht_doppelt():
    import app.main  # noqa: F401

    installiere_zugriffslog_maskierung()
    installiere_zugriffslog_maskierung()
    filter_ = [f for f in logging.getLogger(ZUGRIFFSLOGGER).filters if isinstance(f, ZugriffslogMaskierung)]
    assert len(filter_) == 1


def test_filter_ignoriert_fremde_eintraege():
    eintrag = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "Hallo %s", ("welt",), None)
    assert ZugriffslogMaskierung().filter(eintrag) is True
    assert eintrag.getMessage() == "Hallo welt"
