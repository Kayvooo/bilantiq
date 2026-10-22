# Rechnungsvorlagen: Redesign Oktober 2026

Status: GEBAUT, lokal geprüft; noch nicht produktiv bereitgestellt. Auftrag: vorhandene Vorlagen anhand der fünf vom Nutzer
gelieferten Rechnungsbeispiele sichtbar hochwertiger gestalten.

## Aufbau

Bestehende React/TypeScript-Auswahl und Python/ReportLab-Ausgabe beibehalten.
`backend/app/core/document_layouts.py` kapselt neue Layouts mit gemeinsamem
Zeilenumbruch und Mehrseitenaufbau. `document_pdf.py` bleibt die öffentliche
Schnittstelle für Rechnungen, Angebote, Auftragsbestätigungen und Lieferscheine.
Die elf gespeicherten Vorlagen-IDs bleiben kompatibel (die ursprünglich erwähnten Tarifprüfungen sind inzwischen entfallen).
Keine Migration, keine Änderung von Rechnungsbeträgen oder Steuerberechnungen.

## Gestaltung

Weiß #FFFFFF, Text #20282C, Sekundärtext #65717A, Linien #DCE2E5,
Petrol #123D3A, optionale Kundenfarbe (z. B. Kupfer #B56518 / Blau #193B83).
Helvetica für klare Geschäftsdokumente; Times nur für die elegante Variante,
Courier nur für die technische. Beträge rechtsbündig, Anschriften linksbündig.

Layouts: Geschäftsbrief, farbiger Tabellenkopf, reduziertes Studio-Layout,
kompakte Tabelle, elegante Serifenvorlage, breiter Briefkopf, schmale geschwungene
Seitenleiste, feiner Rahmen, hervorgehobene Summe, technische Tabelle und
dezentes Wasserzeichen. Die Seitenleiste darf keine Datenspalten verdrängen.

```text
Logo / Absender                       Dokumenttitel
Empfänger                             Nummer / Datum / Ziel
Leistung                       Menge  Preis  Steuer  Betrag
Zahlungshinweis                             Netto / Gesamt
Fußzeile                                     Seite n von N
```

## Prüfung

- Alle elf Vorlagen, vier Farbvarianten, De/En, Logo-Größen, Toggles.
- Lange Beschreibungen vollständig umbrechen, auch über Seiten hinweg.
- Korrekte Seitennummern, wiederholte Tabellenköpfe, Fußzeilen ohne Überlagerung.
- Lieferschein weiterhin ohne Preise; Betrag/Datum nicht als Grafik rasterisieren.
- PDF-Beispiele visuell prüfen, vollständige Backend-Suite und Frontend-Build.
- Beispiele enthalten ausschließlich fiktive Daten; Referenzlogos werden nicht kopiert.

Deployment ist ein separater Schritt; lokale Vorschauen sind keine Live-Freigabe.

## Umsetzung und reproduzierbare Vorschau

- Elf vorhandene IDs bleiben erhalten; alte, abgeschnittene Tabellenlayouts sind
  durch einen gemeinsamen gemessenen Seitenplan ersetzt. Zahlen bleiben Text.
- Echte Miniaturbilder aus dem PDF-Renderer in `frontend/public/invoice-designs/`,
  mit den vorhandenen Radio-Eingaben und sichtbarem Tastaturfokus auswählbar.
- Deutsche Zahlendarstellung, automatische Kontrastfarbe auf farbigen Flächen.
- Keine Referenzlogos oder Stockgrafiken übernommen.
- Muster generieren: aus `backend/` mit
  `python scripts/preview_invoice_designs.py data/invoice-design-preview --thumbnails ../frontend/public/invoice-designs`.
  Der Katalog enthält Lesezeichen mit den Vorlagennamen.
- HTTP-Prüfung: `python scripts/smoke_invoice_designs.py`. Startet einen
  temporären Server auf Loopback mit eigener Testdatenbank, Registrierung/MFA
  und fiktivem Pro-Mandanten; beendet ihn nach elf PDF-Abrufen wieder.
- Sichtprüfung aller elf PDF-Muster; Galerie mit denselben CSS-Klassen und
  Labels bei 390 und 1280 Pixel geprüft (kein horizontaler Überlauf, elf Bilder
  vollständig geladen). Das ersetzt keinen End-to-End-Test auf einem echten Handy.
- TypeScript-Prüfung, oxlint und Vite-Produktionsbuild erfolgreich.
- Abschließende komplette Backend-Suite: **393 Tests bestanden**, davon 68 neue
  Layout-Regressionstests. Anschließend nochmals 68 Layouttests am finalen Stand
  bestanden. Bestehende Deprecation-Warnungen von Starlette/Alembic bleiben bestehen.
- Erneuter Live-Smoke mit Registrierung/MFA und elf PDF-Vorlagen erfolgreich.

Die technischen Tests benötigen eine eigene SQLite-Testdatenbank (siehe `tests/conftest.py`).
Keine Produktivschlüssel oder Kundendaten wurden verwendet.
