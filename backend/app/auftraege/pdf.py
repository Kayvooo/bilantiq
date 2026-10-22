from app.auftraege.models import Auftragsbestaetigung, Lieferschein
from app.auth.models import Mandant
from app.core.document_pdf import DocumentPosition, LieferPosition, render_document_pdf, render_lieferschein_pdf


def render_auftragsbestaetigung_pdf(mandant: Mandant, ab: Auftragsbestaetigung) -> bytes:
    kontakt = ab.kontakt
    return render_document_pdf(
        mandant,
        titel_prefix="auftragsbestaetigung",
        nummer=ab.nummer,
        ist_entwurf=False,
        entwurf_hinweis="",
        kontakt_name=kontakt.name,
        kontakt_strasse=kontakt.strasse,
        kontakt_ort_zeile=f"{kontakt.plz or ''} {kontakt.ort or ''}".strip(),
        kontakt_land=kontakt.land,
        datum_label="erstellt_am",
        datum=ab.erstellt_am.date(),
        folgedatum_label="angebot_vom",
        folgedatum=ab.quote.erstellt_am.date(),
        positionen=[
            DocumentPosition(beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz)
            for p in ab.positionen
        ],
        waehrung=ab.waehrung,
        netto_gesamt=ab.netto_gesamt,
        ust_gesamt=ab.ust_gesamt,
        brutto_gesamt=ab.brutto_gesamt,
        kundennummer=kontakt.kundennummer,
    )


def render_lieferschein_pdf_for(mandant: Mandant, lieferschein: Lieferschein) -> bytes:
    kontakt = lieferschein.kontakt
    return render_lieferschein_pdf(
        mandant,
        nummer=lieferschein.nummer,
        kontakt_name=kontakt.name,
        kontakt_strasse=kontakt.strasse,
        kontakt_ort_zeile=f"{kontakt.plz or ''} {kontakt.ort or ''}".strip(),
        kontakt_land=kontakt.land,
        lieferdatum=lieferschein.lieferdatum,
        positionen=[LieferPosition(beschreibung=p.beschreibung, menge=p.menge) for p in lieferschein.positionen],
        kundennummer=kontakt.kundennummer,
    )
