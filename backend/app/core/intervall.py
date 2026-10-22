"""Geteilte Wiederholungslogik fuer wiederkehrende Rechnungen und Ausgaben
(app/wiederkehrend/), damit beide dieselbe Kalenderarithmetik verwenden."""
import calendar
from datetime import date

INTERVALLE = ("monatlich", "quartalsweise", "jaehrlich")


def add_months(datum: date, months: int) -> date:
    """Monatsueberlauf selbst behandeln, Tag auf den letzten Tag des Zielmonats
    kappen (31. Jan + 1 Monat = 28./29. Feb statt eines ValueError)."""
    month_index = datum.month - 1 + months
    year = datum.year + month_index // 12
    month = month_index % 12 + 1
    day = min(datum.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def naechster_termin(datum: date, intervall: str) -> date:
    if intervall == "monatlich":
        return add_months(datum, 1)
    if intervall == "quartalsweise":
        return add_months(datum, 3)
    return add_months(datum, 12)  # jaehrlich
