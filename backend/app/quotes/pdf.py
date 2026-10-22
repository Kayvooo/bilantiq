from app.auth.models import Mandant
from app.core.document_pdf import DocumentPosition, render_document_pdf
from app.quotes.models import Quote


def render_quote_pdf(mandant: Mandant, quote: Quote) -> bytes:
    kontakt = quote.kontakt
    return render_document_pdf(
        mandant,
        titel_prefix="angebot",
        nummer=quote.nummer,
        ist_entwurf=quote.status == "entwurf",
        entwurf_hinweis="entwurf_hinweis_angebot",
        kontakt_name=kontakt.name,
        kontakt_strasse=kontakt.strasse,
        kontakt_ort_zeile=f"{kontakt.plz or ''} {kontakt.ort or ''}".strip(),
        kontakt_land=kontakt.land,
        datum_label="erstellt_am",
        datum=quote.erstellt_am.date(),
        folgedatum_label="gueltig_bis",
        folgedatum=quote.gueltig_bis,
        positionen=[
            DocumentPosition(beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz)
            for p in quote.positionen
        ],
        waehrung=quote.waehrung,
        netto_gesamt=quote.netto_gesamt,
        ust_gesamt=quote.ust_gesamt,
        brutto_gesamt=quote.brutto_gesamt,
        kundennummer=kontakt.kundennummer,
    )
