# Branding-Migration 2026

Plan erstellt vor der Implementierung am 07.10.2026. Autorisierung: vollständige
Branding-Prüfung und Umsetzung auf separatem Feature-Branch durch den Owner.
Basis: `main` bei `ecbf3edde43395a3e60c85ae1c4dcca5a2255f9c`.
Branch: `feature/branding-2026`. Kein Merge und kein Deployment in diesem Auftrag.

## Ziel, Architektur und Dateistruktur

Bilantiq ist die Buchhaltungsanwendung für Selbstständige und kleine Unternehmen;
Rechnungen, Belegerfassung und Auswertungen bleiben die Kernabläufe. Das bestehende
React-19-/TypeScript-/Vite-Frontend und FastAPI-Backend bleiben erhalten. Keine neue
Bibliothek, API oder Schriftanfrage. Der Brandguide 2.0 ersetzt die alte Richtung A.

- `frontend/public/brand/`: originale Logo-Pfade, Icons, Manifest und lokale Fonts.
- `frontend/src/styles/brand.css`: gelieferte Farb-/Typografie-/Radius-Tokens.
- `frontend/src/styles/tokens.css`: semantische Zuordnung für vorhandene Komponenten.
- `frontend/src/index.css`: Typografie, Controls, Flächen, Navigation und Diagramme.
- `frontend/src/components/Brand.tsx`, `DonutChart.tsx`: ausschließlich Präsentation.
- `frontend/index.html`: Icon-Verweise, Manifest und Theme-Farbe.
- `docs/specs/branding-migration-2026.md`: Plan, Annahmen und Abnahme.
- `docs/specs/branding-2026-assets.json`: vollständiges Paketinventar mit Hashes.

## Vollständige Paketprüfung

`Bilantiq_Brandpaket_2026.zip`: 200 Dateien; ZIP-CRC fehlerfrei. Alle 199 Einträge des
Asset-Manifests sind vorhanden und stimmen bytegenau in der angegebenen Größe überein.
Das Manifest selbst ist nachvollziehbar nicht im eigenen Manifest enthalten.
26 PDF-Seiten und vollständige Textfassung geprüft; alle PDF-Seiten gerendert und
als Kontaktbögen visuell geprüft. 107 PNGs und ein ICO dekodiert, 76 SVGs geparst,
JSON/Manifest eingelesen und das Generierungsskript syntaktisch geprüft, nicht ausgeführt.
34 Logo-Quelldateien sind Duplikate der freigegebenen SVG-Exports.
Die beiden variablen Schriften passen zu den vorhandenen Fonts; OFL-Lizenzen bleiben dabei.

| Paketbereich | Zuordnung im Repository / Entscheidung |
| --- | --- |
| 01 Brandguide | Verbindliche Richtung für diese Migration; Beispiele sind keine Produkt-Spezifikation. |
| 02 Logos | Horizontales Waldgrün-SVG auf hellen Flächen; Wortmarke/Symbol ebenfalls original übernehmen. Weiße, limettenfarbene, gestapelte und quadratische PNG-Varianten bleiben für passende spätere Anwendungen verfügbar. |
| 03 Social Media | Profile, Feed und Story geprüft. Kein Social-Publisher und keine Marketing-Landingpage im aktuellen Repository; keine Einbindung in Arbeitsmasken. |
| 04 App und Favicons | SVG/ICO, Apple-Icon, 192/512-PNG und Maskable-Icon übernehmen; relatives Manifest unter `/brand/` belassen. Kein Service Worker und keine Offline-Finanzfunktion ergänzen. |
| 05 Design Tokens | CSS-Farbmaster und JSON übernehmen; CSV und Kontrastwerte gegengeprüft. Vorhandene semantische Variablennamen auf die neuen Werte abbilden. |
| 06 Schriften | Manrope 200–800 und IBM Plex Sans 100–700 lokal; vorhandene Dateien mit Originalen abgleichen. Keine Schriftmigration erforderlich. |
| 07 Quelldateien | Originalpfade verwenden, nicht nachbauen; Inventar dokumentieren. Generator nicht in Runtime oder Build integrieren. |
| 08 Geschäftsausstattung | SVG-Vorlagen geprüft; keine Anwendung in den vom Mandanten konfigurierten Rechnungs-PDFs. Platzhalter-Kontaktdaten und sRGB sind keine druckfertige Produktionsfreigabe. |

## Migrationsmatrix

| Bereich | Vorher | Ziel / betroffene Stellen |
| --- | --- | --- |
| Primärlogo | Alte Petrol-Wortmarke | Horizontales originales Q+Wortmarken-SVG, unverzerrt, sichtbare Breite mindestens 160 px, Schutzraum mindestens ein Viertel der sichtbaren Höhe. `Brand`, Auth-/Demo-Kopfzeilen. |
| Marke / Aktionen | Petrol `#123D3A` | Waldgrün `#143D2B`, Hover `#0D2D1E`, gedrückt `#082216`; weiße Beschriftung. |
| Akzent | Lavendel `#C7BEFF` | Limette `#D8F36A`, immer Waldgrün als Text; Auswahl, Bottom-Nav, Sidebar, Promo und Summenflächen. Kein Erfolgs-Ersatz. |
| Hintergrund / Text | Wolke / `#172B29` | Papier `#F7F8F2`, Ink `#18251D`, Sekundärtext `#526258`, Weiß. |
| Konturen / Fokus | `#748782` / Violett | Controls `#7B8B7F`; dekorative Linien `#DDE3D9`; Fokus `#245CA6`, 3 px Ring/3 px Abstand. |
| Statusfarben | Alte Erfolg/Warnung/Fehler/Info-Werte | `#246443` / `#835000` / `#B23838` / `#245CA6` samt gelieferten hellen Flächen; bestehende Labels und Statuszuordnung unverändert. |
| Typografie | Manrope / IBM Plex Sans | Familien bereits korrekt; mobile H1 30/38, Desktop 40/48, H2 24/32 bzw. 28/36. Finanzzahlen Plex Sans mit tabellarischen Ziffern; Tabellen 14/20, Labels 600. |
| Controls / Karten | Radien 8/12/20 | 10/16/24 px; Buttons mindestens 44 px, deaktiviert Papier/Sekundärtext ohne Hover; Bewegung 140/220 ms und bestehendes Reduced Motion. |
| Funktionale Icons | 24-px-Raster, Strich 1,8 px, currentColor | Bereits konform, behalten. Q ausschließlich Marke; keine neue Icons-Bibliothek. |
| Diagramme | Limette/Lavendel und hartcodierte Petrol-Abstufungen | Hauptserie Waldgrün, Vergleich Blau auf Papier; weitere Donut-Kategorien mit benannten neutralen Tokens und vorhandener beschrifteter Wertlegende. Berechnungen, Achsen und Daten unverändert. |
| Desktop / Mobil | Sidebar ab 1024 px / Bottom-Nav | Struktur und Ziele behalten. Sidebar Waldgrün mit weißen Labels, aktive Auswahl Limette; max. Inhalt 1200 px, mobil 20 px Außenrand. |
| App-Metadaten | Altes Favicon / Theme-Petrol | Gelieferte neue Icons/Manifest, Theme-Waldgrün und Papier-Hintergrund. Alte `/favicon.svg`-Adresse weiter mit neuem Inhalt bedienen. |

## Betroffene Komponenten und Scope-Schutz

Direkte TSX-Änderungen sind auf `Brand` und die Farbpalette von `DonutChart` begrenzt.
Über globale Tokens/CSS betroffen: PageHeader, PageState, StatusPill, Sidebar,
BottomNav, GroupedList, BarChart, PdfPreviewFrame und alle Auth-, MFA-, Dashboard-,
Rechnungs-, Kontakt-, Angebots-, Beleg-, Ausgaben-, Anlagen-, Kassenbuch-, Lohn-,
Produkt-, Tarif-, Benutzer-, Einstellungen- und Berichtsansichten einschließlich Demo.
Das Aussehen des Rechnungsdesign-Panels folgt den UI-Tokens, seine Werte bleiben gleich.

Bewusste Ausnahme: `STANDARD_AKZENTFARBE = "#123D3A"` in
`frontend/src/features/auth/RechnungsdesignPanel.tsx` und
`backend/app/core/document_pdf.py` bleibt erhalten. Das ist ein persistierter
Mandanten-/Dokumentdefault mit Rücksetzfunktion, kein UI-Farbtoken. Ebenso bleiben
kundeneigene Logos, Briefpapier und PDF-Vorlagen unberührt. Ein späterer
Dokumentdefault-Wechsel wäre eine eigene Fachentscheidung mit Migrationsstrategie.

Keine Änderungen an Backend, Migrationen, AuthFlow, MFA, JWT, Verschlüsselung,
Mandantentrennung, Security-Headern/CSP, API-Clients, Tarifen, OCR/Confidence,
Validierungen, Formular-Handlern, Buchungsregeln oder Zahlen-/Datumsformatierung.
Kein Dark-Theme ohne eigene Vorgaben. Die alte ZIP bleibt als historische Quelle
im Repository; aktuelle Dokumentation kennzeichnet das neue System.

## Reihenfolge und Abnahme

1. Paket/Repository prüfen und diesen Plan vor Implementierung festhalten.
2. Feature-Branch vom geprüften Stand; Original-Assets/Metadaten integrieren.
3. Token-Aliase, Typografie, Controls, Navigation und Diagrammfarben migrieren.
4. `npx tsc -b --noEmit`, `npm run lint`, `npm run build` ausführen.
5. Asset-Pfade, Originaldatei-Hashes, Kontraste und Production-HTTP-Auslieferung prüfen.
6. Diff gegen Basis kontrollieren: ausschließlich Branding/Präsentation/Dokumentation.
   Backend und Feature-/Security-Logik müssen bytegleich bleiben.
7. Änderungen mit deutschem Commit und Co-Author auf dem Feature-Branch sichern.

Ein technischer Build ersetzt keine vollständige authentifizierte Browser-Abnahme.
Status und tatsächliche Prüfergebnisse werden nach Umsetzung hier ergänzt.

## Umsetzung und Abnahme (07.10.2026)

Status: IMPLEMENTIERT und technisch geprüft auf dem Feature-Branch.
Der Plan wurde als eigener erster Commit vor der Implementierung auf GitHub gesichert.

- Typecheck: `npx tsc -b --noEmit`, Exit 0.
- Lint: `npm run lint` (oxlint), Exit 0, keine Meldungen.
- Production-Build: `npm run build`, Exit 0, 87 Module; CSS rund 25,66 kB,
  JavaScript rund 398,10 kB (gzip rund 5,61/99,88 kB).
- Production-HTTP-Smoke über Vite Preview: HTML sowie 15 verlinkte/gezielt geprüfte
  Ressourcen mit Status 200, korrekten Content-Types und bytegenauem Vergleich zum
  Build-Ausgabeverzeichnis. Darunter Bundle/CSS, Logo/Wortmarke/Symbol, beide Fonts,
  favicon.svg/ICO/Apple-Icon, Webmanifest und alle drei Manifest-PNGs.
- Originale integrierte SVGs, Icons, Manifest und Farbmaster-CSS sind bytegleich
  zu den gelieferten Dateien. Schriften und Lizenzen waren bereits bytegleich.
- Acht Kontrastwerte unabhängig nachgerechnet, Abweichung unter 0,001.
- 266 der 278 vorhandenen Repository-Dateien sind bytegleich zur Basis; die zwölf
  geänderten bestehenden Dateien betreffen ausschließlich Branding und Dokumentation.
  Alle Backend-/Migrationsdateien, Feature-Komponenten, API-Clients, Formatierer,
  Navigation, Security-/Infrastrukturkonfiguration und Dependency-Manifeste bleiben
  unverändert. Bei `DonutChart` sind nach Entfernung von Palette/Kommentaren alle
  Berechnungen und das JSX unverändert.
- React-Präsentationsreview: Original-`img` mit Alt-Text/Größen, keine neuen Hooks,
  Requests, Abhängigkeiten oder Zustände; Donut-Legende und Wertdarstellung erhalten.
- `git diff --check` ohne Fehler.

Kleine Formate behalten den Logo-Schutzraum; `object-fit: contain` schützt die
Originalproportionen in der festen Logo-Box. Die blaue Tastaturkontur bekommt auf
der dunklen Sidebar eine weiße Unterlage, damit der Kontrast erhalten bleibt.
Aktive Sidebar-Hoverzustände bleiben Limette/Waldgrün; deaktivierte Controls behalten
ihre bestehende `disabled`-Semantik und erhalten keine Hoveraktion.

Visuelle Frontend-Browser-Abnahme bleibt OFFEN: In dieser Umgebung ist kein Chromium
installiert. Der Playwright-Download scheiterte mit einer ungültigen/trunkierten
ZIP-Antwort. Deshalb keine behaupteten UI-Screenshots oder vollständigen E2E-Tests.
Nachzuholen: echte Desktop-/Mobile-Ansichten (320/390/768/1024/1440 px), Navigation,
Fokus/Hover/Disabled und authentifizierte Formulare mit Demo-Daten. Kein echter
Kundenaccount, kein Finanzdatensatz und kein Produktionssystem wurde dafür verändert.
