"""Local OCR and rule-based field extraction for uploaded receipts.

The extractor deliberately keeps uncertain values below the configurable
``receipt_confidence_threshold``. The decision whether a field is displayed as
``[UNKLAR]`` remains in ``routes.py``; this module only returns values and
heuristic confidence scores through the existing public models.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Protocol

import pytesseract
from pdf2image import convert_from_bytes, pdfinfo_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFPopplerTimeoutError, PDFSyntaxError
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

# Schutz vor Dekompressionsbomben: ein kleines Bild darf nicht Gigapixel entpacken.
Image.MAX_IMAGE_PIXELS = 60_000_000

# Schutz beim PDF-Rendern: ein PDF mit tausenden Seiten oder Plakatformat darf nicht den Arbeitsspeicher fuellen.
# Belege haben selten mehr als ein paar Seiten; weitere Seiten werden nicht per OCR gelesen.
MAX_OCR_SEITEN = 10
MAX_PIXEL_PRO_SEITE = 30_000_000
_RENDER_TIMEOUT_SEKUNDEN = 90

CATEGORIES = [
    "Buerobedarf", "Reisekosten", "Bewirtung", "Software/IT", "Marketing", "Miete",
    "Telekommunikation", "Sonstiges",
]

_AMOUNT_PATTERN = re.compile(
    r"(?<![\d.,])(?:EUR\s*)?(\d{1,3}(?:[.\s]\d{3})*|\d+)[,.](\d{2})(?![.,]?\d)(?:\s*(?:EUR|€))?",
    re.IGNORECASE,
)
# Betraege ohne Nachkommastellen ("Betrag €3,450", "75 EUR"): nur mit Waehrungszeichen,
# sonst waere jede Zahl (Seitenzahl, Jahr) ein Kandidat. Drei Ziffern nach dem Trenner
# sind ein Tausendertrenner -- Geldbetraege haben nie drei Nachkommastellen. \bEUR\b
# verhindert Treffer in "Europaeischen".
_CURRENCY_INTEGER_AMOUNT = re.compile(
    r"(?<![\d.,])(?:(?:€|\bEUR\b)\s*(\d{1,3}(?:[.,]\d{3})+|\d+)|(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:€|\bEUR\b))(?![.,]?\d)",
    re.IGNORECASE,
)
_TOTAL_KEYWORDS = re.compile(
    r"\b(?:gesamt(?:betrag)?|endsumme|endbetrag|zahlbetrag|betrag|brutto(?:betrag)?|zu\s+zahlen|summe|total)\b",
    re.IGNORECASE,
)
_SUBTOTAL_KEYWORDS = re.compile(r"\b(?:zwischensumme|netto(?:summe|-?betrag)?)\b", re.IGNORECASE)
# Drei Stufen: "primary" ist das Belegdatum, "secondary" ein brauchbarer Ersatz
# (Leistungs-/Bankdatum), "ignore" sind Fristen, die nie das Belegdatum sind. Reihenfolge
# der Alternativen zaehlt nicht fuer den Treffer (der am weitesten links gewinnt), \bdatum\b
# greift absichtlich nicht innerhalb von Komposita wie "Faelligkeitsdatum".
_DATE_LABELS = re.compile(
    r"(?P<ignore>f[aä]llig(?:keits?(?:datum)?)?(?:\s+(?:am|bis))?|zahlungsziel|zahlbar\s+bis|zahlungsfrist|geburtsdatum)"
    r"|(?P<primary>rechnungsdatum|belegdatum|ausstellungsdatum|ausgestellt\s+am|rechnung\s+vom|\bdatum\b)"
    r"|(?P<secondary>leistungsdatum|lieferdatum|leistungszeitpunkt|wertstellungsdatum|buchungsdatum|veranlassungsdatum)",
    re.IGNORECASE,
)
_DATE_LABEL_MAX_GAP = 40
_DATE_PATTERNS = (
    re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"),
)
_VAT_CONTEXT = r"(?:mwst\.?|ust\.?|umsatzsteuer|mehrwertsteuer)"
_VAT_PATTERNS = (
    re.compile(rf"\b{_VAT_CONTEXT}\s*(?:satz)?\s*[:=]?\s*(\d{{1,2}}(?:[.,]\d{{1,2}})?)\s*%", re.IGNORECASE),
    re.compile(rf"(?<!\d)(\d{{1,2}}(?:[.,]\d{{1,2}})?)\s*%\s*{_VAT_CONTEXT}\b", re.IGNORECASE),
)
_SUPPORTED_VAT_PATTERN = re.compile(r"(?<!\d)(0|7|19)(?:[.,]0{1,2})?\s*%(?!\d)", re.IGNORECASE)
_COMPANY_SUFFIX = re.compile(
    r"\b(?:gmbh(?:\s*&\s*co\.?\s*kg)?|ag|ug(?:\s*\(haftungsbeschraenkt\))?|kg|ohg|e\.?\s*k\.?)\b",
    re.IGNORECASE,
)
# Kein schliessendes \b vor der Gruppe: deutsche Komposita haengen diese Woerter
# direkt an ("Rechnungsnummer", "Kundennummer") -- ein \b davor wuerde nie greifen,
# weil zwischen zwei Wortzeichen keine Wortgrenze liegt. tel/fax behalten ihr
# eigenes \b, sonst wuerde z.B. "Telekom" faelschlich als Rauschen gelten.
_VENDOR_NOISE = re.compile(
    r"\b(?:kassenbon|rechnung|quittung|beleg|lieferschein|steuer(?:nummer|-nr)|ust-id|"
    r"tel(?:efon)?\b|fax\b|www\.|https?://|datum|kunden?|filiale|bedienung|kasse|"
    r"hallo|guten\s+tag|sehr\s+geehrte|liebe|generiert|erstellt\s+am|iban|bic\b)",
    re.IGNORECASE,
)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Buerobedarf": (
        "bürobedarf", "buerobedarf", "schreibwaren", "papier", "toner", "druckerpatrone", "copyshop",
        "office depot", "stift", "ordner", "büromaterial", "bueromaterial", "büroartikel", "bueroartikel",
        "druckerpapier", "briefumschläge", "briefumschlaege", "kugelschreiber", "aktenordner", "haftnotizen",
    ),
    "Reisekosten": (
        "deutsche bahn", "db vertrieb", "bahnticket", "bahn", "flixbus", "taxi", "uber", "hotel",
        "flug", "airline", "mietwagen", "parkhaus", "tankstelle", "übernachtung", "uebernachtung",
        "fahrkarte", "zugfahrt", "kraftstoff", "diesel", "benzin", "autovermietung", "lufthansa",
        "ryanair", "easyjet", "booking.com", "parkgebühr", "parkgebuehr", "maut",
    ),
    "Bewirtung": (
        "restaurant", "gasthaus", "gastronomie", "café", "cafe", "bistro", "imbiss", "pizzeria",
        "bäckerei", "baeckerei", "lieferando", "speisen", "getränke", "getraenke", "mittagessen",
        "abendessen", "kantine", "kaffee", "catering",
    ),
    "Software/IT": (
        "software", "hosting", "webhosting", "domain", "cloud", "saas", "microsoft 365", "adobe",
        "github", "google workspace", "aws", "rechenzentrum", "lizenz", "ionos", "strato", "hetzner",
        "vserver", "server-miete", "jetbrains", "dropbox", "notion", "slack", "zoom", "openai",
        "app store", "play store", "online-speicher",
    ),
    "Marketing": (
        "marketing", "werbung", "google ads", "meta ads", "facebook ads", "instagram ads", "anzeige",
        "flyer", "werbemittel", "druckerei", "visitenkarten", "werbeanzeige", "social media",
        "newsletter", "plakat", "seo",
    ),
    "Miete": ("miete", "mietzins", "vermieter", "nebenkosten", "pacht", "kaltmiete", "warmmiete", "coworking"),
    "Telekommunikation": (
        "vodafone", "telekom", "deutsche telekom", "o2", "1&1", "1und1", "mobilfunk",
        "mobilfunkrechnung", "handyvertrag", "festnetz", "dsl-anschluss", "internetanschluss",
        "telefonie", "sim-karte", "mobilfunkvertrag", "congstar", "freenet", "mobilcom", "telefónica",
        "telefonica",
    ),
}


class ExtractedField(BaseModel):
    wert: str | None
    confidence: float


class ReceiptExtraction(BaseModel):
    betrag: ExtractedField
    datum: ExtractedField
    anbieter: ExtractedField
    ust_satz: ExtractedField
    kategorie_vorschlag: ExtractedField
    begruendung: str


class ExtractionUnavailable(Exception):
    """Local extraction could not run, for example because OCR is unavailable."""


class ReceiptExtractor(Protocol):
    def extract(self, file_bytes: bytes, mime_type: str) -> ReceiptExtraction: ...


def _empty_field() -> ExtractedField:
    return ExtractedField(wert=None, confidence=0.0)


def _non_empty_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _decimal_from_match(match: re.Match[str]) -> Decimal | None:
    whole = re.sub(r"[.\s]", "", match.group(1))
    try:
        value = Decimal(f"{whole}.{match.group(2)}")
    except InvalidOperation:
        return None
    return value if Decimal("0") < value <= Decimal("10000000") else None


def _amounts_in_line(line: str) -> list[Decimal]:
    values = [value for match in _AMOUNT_PATTERN.finditer(line) if (value := _decimal_from_match(match))]
    for match in _CURRENCY_INTEGER_AMOUNT.finditer(line):
        try:
            value = Decimal(re.sub(r"[.,]", "", match.group(1) or match.group(2)))
        except InvalidOperation:
            continue
        if Decimal("0") < value <= Decimal("10000000"):
            values.append(value)
    return values


def _verified_brutto(values: list[Decimal]) -> Decimal | None:
    """Erkennt eine Netto/USt-Betrag/Brutto-Zeile (z.B. "Gesamt 80,79 3,19 83,98"),
    wie sie auf Telekom-/Versicherungsrechnungen als Summenzeile ueblich ist.
    Spaltenreihenfolge ist dabei egal: der Wert, der der Summe der beiden anderen
    entspricht, ist rechnerisch eindeutig der Bruttobetrag."""
    if len(values) != 3:
        return None
    for index, candidate in enumerate(values):
        rest = [value for other_index, value in enumerate(values) if other_index != index]
        if rest[0] + rest[1] == candidate:
            return candidate
    return None


def _extract_amount(lines: list[str]) -> ExtractedField:
    labelled: list[Decimal] = []
    all_amounts: list[Decimal] = []
    verified: list[Decimal] = []
    for line in lines:
        values = _amounts_in_line(line)
        all_amounts.extend(values)
        if _TOTAL_KEYWORDS.search(line) and not _SUBTOTAL_KEYWORDS.search(line):
            brutto = _verified_brutto(values)
            if brutto is not None:
                verified.append(brutto)
            else:
                labelled.extend(values)

    if len(set(verified)) == 1:
        return ExtractedField(wert=f"{verified[0]:.2f}", confidence=0.92)
    labelled.extend(verified)

    if labelled:
        distinct = sorted(set(labelled))
        value = max(distinct)
        confidence = 0.92 if len(distinct) == 1 else 0.5
        return ExtractedField(wert=f"{value:.2f}", confidence=confidence)
    if all_amounts:
        # Useful candidate, but without a total label it must remain [UNKLAR].
        return ExtractedField(wert=f"{max(all_amounts):.2f}", confidence=0.5)
    return _empty_field()


def _parse_date_match(match: re.Match[str], *, iso: bool) -> date | None:
    try:
        if iso:
            year, month, day = (int(match.group(i)) for i in range(1, 4))
        else:
            day, month, year = (int(match.group(i)) for i in range(1, 4))
            if year < 100:
                year += 2000
        parsed = date(year, month, day)
    except ValueError:
        return None
    return parsed if 2000 <= parsed.year <= 2100 else None


def _extract_date(lines: list[str]) -> ExtractedField:
    candidates: list[tuple[date, str | None]] = []
    pending_tier: str | None = None
    for line in lines:
        labels = [(match.start(), match.end(), match.lastgroup) for match in _DATE_LABELS.finditer(line)]
        found_here = False
        for index, pattern in enumerate(_DATE_PATTERNS):
            for match in pattern.finditer(line):
                parsed = _parse_date_match(match, iso=index == 1)
                if parsed is None:
                    continue
                found_here = True
                # Jedes Datum gehoert zum naechsten Label links davon in derselben Zeile
                # ("Leistungsdatum: ... Zahlungsziel: ..." enthaelt zwei verschiedene Daten).
                tier = next(
                    (
                        kind
                        for _, end, kind in reversed(labels)
                        if end <= match.start() and match.start() - end <= _DATE_LABEL_MAX_GAP
                    ),
                    None,
                )
                if tier is None and not labels:
                    tier = pending_tier
                if tier != "ignore":
                    candidates.append((parsed, tier))
        # OCR trennt ein Label wie "Rechnung vom" gelegentlich vom Datum in die
        # naechste Zeile (Layout-/Spaltenumbruch) -- das Label bleibt dann fuer
        # genau eine weitere Zeile gueltig, statt zu verfallen.
        last_kind = labels[-1][2] if labels else None
        pending_tier = last_kind if last_kind in {"primary", "secondary"} and not found_here else None

    if not candidates:
        return _empty_field()
    primary = {candidate for candidate, tier in candidates if tier == "primary"}
    secondary = {candidate for candidate, tier in candidates if tier == "secondary"}
    all_dates = {candidate for candidate, _ in candidates}
    if len(primary) == 1:
        return ExtractedField(wert=next(iter(primary)).isoformat(), confidence=0.92)
    if not primary and len(secondary) == 1:
        return ExtractedField(wert=next(iter(secondary)).isoformat(), confidence=0.85)
    if len(all_dates) == 1:
        return ExtractedField(wert=next(iter(all_dates)).isoformat(), confidence=0.85)
    return ExtractedField(wert=None, confidence=0.3)


def _normalise_vat(raw: str) -> str | None:
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None
    if value not in {Decimal("0"), Decimal("7"), Decimal("19")}:
        return None
    return f"{value:.2f}"


def _extract_vat(text: str) -> ExtractedField:
    contextual = {
        value
        for pattern in _VAT_PATTERNS
        for match in pattern.finditer(text)
        if (value := _normalise_vat(match.group(1))) is not None
    }
    if len(contextual) == 1:
        return ExtractedField(wert=next(iter(contextual)), confidence=0.92)
    if len(contextual) > 1:
        return ExtractedField(wert=None, confidence=0.3)

    supported = {
        value for match in _SUPPORTED_VAT_PATTERN.finditer(text)
        if (value := _normalise_vat(match.group(1))) is not None
    }
    if len(supported) == 1:
        return ExtractedField(wert=next(iter(supported)), confidence=0.75)
    if len(supported) > 1:
        return ExtractedField(wert=None, confidence=0.25)
    return _empty_field()


_DOMAIN_HINT = re.compile(r"\b[a-z0-9-]+\.(?:de|com|net|org|eu|info)\b", re.IGNORECASE)


def _find_impressum_line(lines: list[str]) -> str | None:
    """Fallback ausserhalb der ersten 8 Zeilen: eine Impressum-/Fusszeile, die Firma
    (mit Rechtsform) und eigene Domain nennt -- Pflichtangabe nach §5 DDG, deshalb auf
    praktisch jeder deutschen Geschaeftsrechnung vorhanden. Die Domain-Bedingung
    verhindert, dass eine beliebige spaeter im Dokument erwaehnte GmbH (z.B. in einer
    Kunden-/Adresszeile) faelschlich als Anbieter gilt."""
    for line in lines:
        stripped = line.strip(" \t|®©™*•_-=~:;")
        if _VENDOR_NOISE.search(stripped) or "@" in stripped or not _DOMAIN_HINT.search(stripped):
            continue
        match = _COMPANY_SUFFIX.search(stripped)
        if not match:
            continue
        candidate = stripped[: match.end()].strip(" \t,;")
        letters = sum(character.isalpha() for character in candidate)
        digits = sum(character.isdigit() for character in candidate)
        if letters < 3 or digits > letters or len(candidate) > 80:
            continue
        return candidate
    return None


_TRANSFER_ACCOUNT_HINT = re.compile(r"\b(?:iban|bic)", re.IGNORECASE)
_TRANSFER_WORDS = re.compile(r"[uü]berweisung|\bsepa\b|wertstellung|zahlungsbest[aä]tigung", re.IGNORECASE)
_RECIPIENT_HEADER = re.compile(r"(?:zahlungs)?empf.?nger(?:daten)?\b[\s:]*(.*)$", re.IGNORECASE)
_RECIPIENT_NAME = re.compile(r"(?:name|kontoinhaber|inhaber)\b[\s:]*(.+)$", re.IGNORECASE)


def _usable_name(value: str) -> str | None:
    value = value.strip(" \t|:;,")
    letters = sum(character.isalpha() for character in value)
    digits = sum(character.isdigit() for character in value)
    if letters < 3 or digits > letters or len(value) > 80:
        return None
    return value


def _find_transfer_recipient(lines: list[str]) -> str | None:
    """Bei Ueberweisungsbestaetigungen (Bank-/Fintech-PDFs) steht oben der eigene
    Kontoinhaber, der Anbieter ist der Zahlungsempfaenger. Nur aktiv, wenn das
    Dokument nach einer Ueberweisung aussieht (IBAN/BIC plus Ueberweisungs-Woerter) --
    auf normalen Rechnungen meint "Empfaenger" den Kunden."""
    text = "\n".join(lines)
    if not (_TRANSFER_ACCOUNT_HINT.search(text) and _TRANSFER_WORDS.search(text)):
        return None
    for index, line in enumerate(lines):
        header = _RECIPIENT_HEADER.match(line.strip(" \t|:"))
        if not header:
            continue
        if name := _usable_name(header.group(1)):
            return name
        for following in lines[index + 1 : index + 5]:
            name_match = _RECIPIENT_NAME.match(following.strip(" \t|"))
            if name_match and (name := _usable_name(name_match.group(1))):
                return name
    return None


def _extract_vendor(lines: list[str]) -> ExtractedField:
    if recipient := _find_transfer_recipient(lines):
        return ExtractedField(wert=recipient, confidence=0.8)
    weak: ExtractedField | None = None
    for index, line in enumerate(lines[:8]):
        line = line.strip(" \t|®©™*•_-=~:;")
        if _VENDOR_NOISE.search(line) or "@" in line:
            continue
        letters = sum(character.isalpha() for character in line)
        digits = sum(character.isdigit() for character in line)
        if letters < 3 or digits > letters or len(line) > 80:
            continue
        if re.fullmatch(r"[\W_]+", line):
            continue
        if suffix_match := _COMPANY_SUFFIX.search(line):
            # Bis zum Ende der Rechtsform abschneiden: sonst würde eine Zeile wie
            # "Muster GmbH, Musterallee 1, 12345 Musterstadt" die Adresse mit als
            # "Anbieter" übernehmen.
            candidate = line[: suffix_match.end()].strip(" \t,;")
            confidence = 0.9 if index <= 2 else 0.8
            return ExtractedField(wert=candidate, confidence=confidence)
        if weak is None:
            # Ohne erkennbare Rechtsform (GmbH/AG/...) ist eine spaeter im Dokument
            # gefundene Zeile ein schwacher Hinweis, kein Beleg -- die Konfidenz faellt
            # ab Zeile 2 unter receipt_confidence_threshold, damit z.B. eine
            # Kundenanrede oder Zeitraumangabe als [UNKLAR] markiert wird statt als
            # sicherer (aber falscher) Anbieter zu erscheinen.
            weak = ExtractedField(wert=line, confidence=max(0.4, 0.72 - index * 0.06))

    # Kein Rechtsform-Suffix unter den ersten 8 Zeilen (z.B. ein mehrspaltiges
    # Layout, das die OCR-Lesereihenfolge durcheinanderbringt) -- viele Rechnungen
    # nennen die Firma zusaetzlich in der Impressum-Fusszeile.
    if impressum := _find_impressum_line(lines[8:]):
        return ExtractedField(wert=impressum, confidence=0.85)
    return weak if weak is not None else _empty_field()


def _keyword_present(text: str, keyword: str) -> bool:
    # Deutsche Komposita haengen das Stichwort hinten an ("Büromiete", "Buchhaltungs-
    # software"). Fuer ausreichend lange Woerter darf deshalb ein Wortanfang davor stehen;
    # kurze Woerter (uber, flug, bahn, o2) bleiben streng, sonst gaebe es zu viele Treffer.
    if len(keyword) >= 5 and keyword.replace(" ", "").isalpha():
        return re.search(rf"{re.escape(keyword)}(?!\w)", text, re.IGNORECASE) is not None
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE) is not None


def _extract_category(text: str) -> tuple[ExtractedField, str]:
    matches: dict[str, list[str]] = {
        category: [keyword for keyword in keywords if _keyword_present(text, keyword)]
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    matches = {category: keywords for category, keywords in matches.items() if keywords}
    if not matches:
        return (
            ExtractedField(wert="Sonstiges", confidence=0.3),
            "Keine eindeutigen Kategorie-Schluesselwoerter erkannt; Sonstiges ist nur ein unsicherer Vorschlag.",
        )

    counts = Counter({category: len(keywords) for category, keywords in matches.items()})
    best_count = max(counts.values())
    winners = [category for category, count in counts.items() if count == best_count]
    if len(winners) != 1:
        return (
            ExtractedField(wert="Sonstiges", confidence=0.4),
            "Mehrdeutige Kategorie-Schluesselwoerter erkannt; der Vorschlag muss geprueft werden.",
        )

    category = winners[0]
    keywords = matches[category]
    confidence = min(0.95, 0.72 + 0.08 * (len(keywords) - 1))
    explanation = f"Kategorie {category} anhand erkannter Begriffe: {', '.join(keywords[:3])}."
    return ExtractedField(wert=category, confidence=confidence), explanation


def parse_ocr_text(raw_text: str) -> ReceiptExtraction:
    """Parse already extracted OCR text without invoking OCR (also used by tests)."""

    lines = _non_empty_lines(raw_text)
    if not lines:
        return ReceiptExtraction(
            betrag=_empty_field(),
            datum=_empty_field(),
            anbieter=_empty_field(),
            ust_satz=_empty_field(),
            kategorie_vorschlag=ExtractedField(wert="Sonstiges", confidence=0.0),
            begruendung="OCR hat keinen auswertbaren Text geliefert.",
        )

    normalised_text = "\n".join(lines)
    category, explanation = _extract_category(normalised_text)
    return ReceiptExtraction(
        betrag=_extract_amount(lines),
        datum=_extract_date(lines),
        anbieter=_extract_vendor(lines),
        ust_satz=_extract_vat(normalised_text),
        kategorie_vorschlag=category,
        begruendung=explanation,
    )


def _prepare_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    if min(image.size) < 1200:
        image = image.resize((image.width * 2, image.height * 2))
    return image


def _dpi_fuer_pdf(file_bytes: bytes) -> int:
    """300 dpi, aber so weit herabgesetzt, dass die erste Seite hoechstens MAX_PIXEL_PRO_SEITE Pixel hat (Plakatformat)."""
    seitengroesse = re.match(r"\s*([\d.]+)\s*x\s*([\d.]+)", str(pdfinfo_from_bytes(file_bytes, timeout=20).get("Page size", "")))
    breite_pt, hoehe_pt = (float(seitengroesse[1]), float(seitengroesse[2])) if seitengroesse else (595.0, 842.0)
    flaeche_zoll = max(breite_pt, 1.0) / 72 * max(hoehe_pt, 1.0) / 72
    return max(20, min(300, int((MAX_PIXEL_PRO_SEITE / flaeche_zoll) ** 0.5)))


class LocalOcrReceiptExtractor:
    def extract(self, file_bytes: bytes, mime_type: str) -> ReceiptExtraction:
        try:
            if mime_type == "application/pdf":
                images = convert_from_bytes(
                    file_bytes, dpi=_dpi_fuer_pdf(file_bytes), thread_count=1, last_page=MAX_OCR_SEITEN,
                    timeout=_RENDER_TIMEOUT_SEKUNDEN,
                )
            elif mime_type in {"image/jpeg", "image/png", "image/webp"}:
                with Image.open(BytesIO(file_bytes)) as source:
                    images = [source.copy()]
            else:
                raise ExtractionUnavailable(f"Nicht unterstuetzter Dateityp fuer OCR: {mime_type}")

            if not images:
                raise ExtractionUnavailable("Die Datei enthaelt keine lesbaren Seiten.")
            raw_text = "\n".join(
                pytesseract.image_to_string(_prepare_image(image), lang="deu", config="--psm 6")
                for image in images
            )
        except ExtractionUnavailable:
            raise
        except (
            pytesseract.TesseractNotFoundError,
            pytesseract.TesseractError,
            PDFInfoNotInstalledError,
            PDFPageCountError,
            PDFSyntaxError,
            PDFPopplerTimeoutError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
            OSError,
            ValueError,
        ) as exc:
            raise ExtractionUnavailable(f"Lokale OCR-Extraktion fehlgeschlagen: {exc}") from exc

        return parse_ocr_text(raw_text)


def get_extractor() -> ReceiptExtractor:
    return LocalOcrReceiptExtractor()
