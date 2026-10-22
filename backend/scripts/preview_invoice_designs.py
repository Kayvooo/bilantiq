"""Generate fictional PDF samples and real thumbnails, never using tenant data.

Run from backend: python scripts/preview_invoice_designs.py OUTPUT_DIRECTORY
Optional --thumbnails DIRECTORY needs Poppler's pdftoppm on PATH.
"""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import date
from decimal import Decimal


def isolated_environment():
    from cryptography.fernet import Fernet
    # Deliberately override real settings: this script is exclusively a demo tool.
    os.environ.update(DATABASE_URL="sqlite://", JWT_SECRET=secrets.token_urlsafe(48),
                      FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                      EMAIL_LOOKUP_SECRET=secrets.token_urlsafe(48),
                      SMTP_HOST="smtp.example.invalid", SMTP_USER="demo@example.invalid",
                      SMTP_PASSWORD="unused")


def sample_mandant(template="modern"):
    from app.auth.models import Mandant
    return Mandant(firmenname="Nordlicht Studio", adresse="Musterstraße 24\n10115 Berlin",
                   rechnungsvorlage=template, design_variante="standard",
                   akzentfarbe="#143D2B", sprache="de", logo_groesse="M",
                   zeige_absenderzeile=True, zeige_positionsbeschreibung=True,
                   zeige_ust_pro_position=True, zeige_fusszeile=True,
                   zeige_seitenzahlen=True, zeige_artikelnummer=False,
                   zeige_kundennummer=False, zeige_kontaktperson=False,
                   zeige_girocode=False, zeige_falz_lochmarken=False,
                   fusszeile_text="Nordlicht Studio · hallo@example.invalid\nMusterrechnung – alle Angaben sind frei erfunden.")


def sample_arguments():
    from app.core.document_pdf import DocumentPosition
    return dict(titel_prefix="rechnung", nummer="RE-2026-0142", ist_entwurf=False,
                entwurf_hinweis="entwurf_hinweis", kontakt_name="Atelier Sommer GmbH",
                kontakt_strasse="Beispielweg 12", kontakt_ort_zeile="20095 Hamburg",
                kontakt_land="Deutschland", datum_label="leistungsdatum", datum=date(2026, 10, 1),
                folgedatum_label="zahlungsziel", folgedatum=date(2026, 10, 15),
                positionen=[
                    DocumentPosition("Markenstrategie\nWorkshop, Positionierung und visuelles Konzept", Decimal(1), Decimal(1200), Decimal(19)),
                    DocumentPosition("Design & Gestaltung\nEntwicklung der Geschäftsausstattung", Decimal(8), Decimal(95), Decimal(19)),
                    DocumentPosition("Übergabe & Dokumentation\nDruckdaten und Gestaltungsleitfaden", Decimal(1), Decimal(240), Decimal(19)),
                ], waehrung="EUR", netto_gesamt=Decimal(2200), ust_gesamt=Decimal(418), brutto_gesamt=Decimal(2618))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--thumbnails", type=Path)
    args = parser.parse_args()
    isolated_environment()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import app.main  # noqa: F401 -- register all ORM models
    import pikepdf
    from app.core.document_pdf import GUELTIGE_VORLAGEN, render_document_pdf
    args.output.mkdir(parents=True, exist_ok=True)
    if args.thumbnails:
        args.thumbnails.mkdir(parents=True, exist_ok=True)
    catalog = pikepdf.Pdf.new()
    for template in GUELTIGE_VORLAGEN:
        path = args.output / f"{template}.pdf"
        mandant = sample_mandant(template)
        # Illustrate the same configurable accent with a few curated examples.
        mandant.akzentfarbe = {"modern": "#A95C28", "balken": "#183D82"}.get(template, "#143D2B")
        path.write_bytes(render_document_pdf(mandant, **sample_arguments()))
        with pikepdf.open(path) as pdf:
            assert len(pdf.pages) == 1, template
            catalog.pages.extend(pdf.pages)
        if args.thumbnails:
            subprocess.run(["pdftoppm", "-png", "-singlefile", "-scale-to", "680", str(path), str(args.thumbnails / template)], check=True)
    with catalog.open_outline() as outline:
        for index, template in enumerate(GUELTIGE_VORLAGEN):
            outline.root.append(pikepdf.OutlineItem(template.capitalize(), index))
    catalog.save(args.output / "Bilantiq-Rechnungsvorlagen.pdf")
    print(f"11 Muster und PDF-Katalog: {args.output}")


if __name__ == "__main__":
    main()
