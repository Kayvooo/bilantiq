# Bilantiq Brand-Redesign

> **Überholt:** Dieses Dokument beschreibt die frühere Richtung A (Petrol/Lavendel). Seit der Branding-Migration 2026 gilt Brandguide 2.0 (Waldgrün/Limette/Papier), siehe `docs/specs/branding-migration-2026.md`. Die Farbwerte unten werden nirgends mehr verwendet.


Historische Spezifikation (September 2026, Version 1.0). Die Branding-Migration
2026 folgt [`branding-migration-2026.md`](branding-migration-2026.md); die unten
stehenden alten Farbwerte beschreiben den damaligen Stand.

Status: GEBAUT · Freigabe: „Durchführung“, fortgesetzt am 06.09.2026.

## Ziel und Architektur

Die bestehende Anwendung übernimmt Richtung A „Ruhige Präzision“ aus dem
bereitgestellten Bilantiq_Brand_Paket (Entwurf 1.0, 05.09.2026). React 19,
TypeScript, Vite und das bestehende FastAPI-Backend bleiben erhalten.
Keine neue Hosting-Plattform, keine neue Komponentenbibliothek.

## Designentscheidung

- Petrol #123D3A: Marke, Hauptaktionen; Lavendel #C7BEFF: aktive Auswahl mit dunkler Schrift.
- Wolke #F3F7F6, Weiß #FFFFFF, Text #172B29, Sekundärtext #536762.
- Manrope für Überschriften, IBM Plex Sans für Text und tabellarische Zahlen.
  Originale variable Schriften und OFL-Lizenzen werden lokal ausgeliefert;
  keine Anfragen an Google Fonts.
- Original-SVG-Wortmarke und Favicons aus dem Paket. Keine nachgebaute Wortmarke.
- Ruhige, klar gerahmte Arbeitsflächen; ein markanter petrolfarbener Ergebnisblock.
  Kein Marketing-Hero vor den Arbeitsdaten. Abstände 4/8/12/16/24/32/48,
  Radien 8/12/20 px, nachvollziehbare Statusfarben und sichtbarer Tastaturfokus.

## Umfang

Registrierung, Anmeldung, MFA, Dashboard, Rechnungen/Kontakte, Angebote,
Belege einschließlich Prüfung, EÜR, Cashflow, UStVA und Konto-Verwaltung.
Gemeinsame Seitenköpfe, Lade-/Fehlerzustände, Uploadfläche, Formulare, Tabellen,
Statusanzeigen und Navigation. Beträge deutsch formatiert, mit Tabellenziffern.
Die Uploadtexte benennen die bereits implementierte lokale Texterkennung korrekt.

Die mobile Bottom-Navigation bleibt einschließlich Reihenfolge erhalten.

## Desktop-Erweiterung (06.09.2026)

Der Owner hat entschieden, nicht länger auf separate Desktop-Referenzen zu
warten: das bestehende Design wird ab `min-width: 1024px` exakt übernommen
und um eine Sidebar erweitert, statt neue Optik zu erfinden. Grundlage ist
kein neuer Entwurf, sondern ein im Bilantiq_Brand_Paket bereits enthaltener,
bis dahin nicht umgesetzter Desktop-Rasterhinweis (12 Spalten, 24 px Steg,
maximal 1200 px Inhalt, Abstände bis 64/96 px, Desktop-H1 40/48 px).

- Ein Breakpoint (`min-width: 1024px`), CSS-only, keine neue Bibliothek.
- `BottomNav` wird ab diesem Breakpoint durch `Sidebar` ersetzt (gleiche Ziele,
  gleiche Reihenfolge, gleiche Aktiv-Farben aus den bestehenden Tokens); beide
  Komponenten liegen im DOM, Sichtbarkeit ist reines CSS, keine JS-Logik.
- Seiteninhalte wachsen von max. 880 px auf 1200 px, das Auth-Formular von
  440 px auf 480 px. `h1` folgt der Desktop-Größe aus dem Brand-Paket.
- Keine mehrspaltige Neuordnung einzelner Formulare, kein Dark-Theme —
  nur der bereits freigegebene Desktop-Rahmen um dieselben Inhalte.

## Navigationsstruktur (06.09.2026)

Der Owner hat als Referenz die tatsächliche sevdesk-Desktop-Navigation
(Screenshot) vorgegeben. Übernommen wurde die Struktur (Gruppen, Reihenfolge,
Unterpunkte), nicht die Optik. `Sidebar` (`frontend/src/components/Sidebar.tsx`)
und die neue Tree-Datenquelle (`frontend/src/lib/navTree.ts`) bilden das
vollständig ab: Erste Schritte, Übersicht, Aufträge, Rechnungen, Ausgaben,
Bank, Steuern, Auswertungen, Lohn, dann „Verwalten" mit Kontakte, Produkte,
Erweiterungen, Einstellungen.

Nur die tatsächlich gebauten Ziele sind klickbar (Übersicht, Angebote,
Rechnungen, Belege, Kontakte, Mahnungen, Wiederkehrende Rechnungen,
Gutschriften, Wiederkehrende Ausgaben, Anlagen, Kassenbuch, Benutzer,
Mein Steuerberater, Auftragsbestätigung, Lieferscheine, Briefpapier, SuSa,
BWA, UStVA, EÜR, Cashflow-Prognose, Lohnvorbereitung, Unternehmen-
Einstellungen — alle bis auf Übersicht/Angebote/Rechnungen/Belege/UStVA/
EÜR/Cashflow/Lohnvorbereitung/Unternehmen kamen am 06./07.09.2026 dazu).
Auftragsbestätigungen entstehen aus einem angenommenen Angebot (feste
Kopie von Positionen/Summen, eigene gaplose Nummer AB-JJJJ-NNNN);
Lieferscheine entstehen aus einer Auftragsbestätigung und tragen bewusst
keine Preise (nur Beschreibung/Menge), mehrere Lieferscheine je
Auftragsbestätigung sind für Teillieferungen erlaubt (eigene Nummer
LS-JJJJ-NNNN). Unter Einstellungen → Briefpapier kann jeder Mandant
Logo, Akzentfarbe, eine von drei Rechnungsvorlagen (Klassisch/Modern/
Minimal) und einen freien Fußzeilentext festlegen — das gilt für alle
PDF-Dokumente (Rechnung, Angebot, Auftragsbestätigung, Lieferschein) ohne
Änderung an deren jeweiligem Code, weil `app/core/document_pdf.py` die
Werte direkt vom Mandanten liest. Eine Live-Vorschau (echtes Beispiel-PDF,
noch ungespeicherte Auswahl inklusive) ist Teil der Seite. "Sonstige
Einnahmen" bleibt Platzhalter — Gutschriften sind ausschließlich Storno-
Korrekturen zu einer bestehenden Rechnung, kein eigenstaendiges Dokument.
Alles andere ist sichtbar, aber deaktiviert ("Bald verfügbar") — keine
neuen Backend-Features in diesem Schritt.
Der „Bank"-Bereich zeigt bewusst nur „Kassenbuch" (ohne Kontoanbindung);
„Konten" und der Zahlungs-Abgleich fehlen komplett, solange finAPI
ausgeklammert bleibt. Die mobile Bottom-Nav und ihre Seitentitel bleiben
unverändert; die vollständige Struktur ist dort weiterhin nur über „Mehr"
erreichbar (jetzt aufgeteilt in Steuern/Auswertungen/Bank/Lohn/Verwalten/
Einstellungen statt einer einzigen „Auswertungen"-Sektion).

## Annahmen und Grenzen

- Die ursprüngliche Farbentscheidung im Paket war offen; die ausdrücklich
  freigegebene Umsetzung folgt Richtung A. Richtung B/C werden nicht vermischt.
- Der Guide definiert kein vollständiges Dark-Theme. Das neue UI folgt bewusst
  dem freigegebenen hellen System, statt alte Navy/Coral-Tokens automatisch
  mit der neuen Marke zu mischen. Ein Dark-Theme braucht eine eigene Abnahme.
- Bestehende APIs, Authentifizierung/MFA, Mandantentrennung und Buchungsregeln
  bleiben unverändert. Keine Datenbanklöschung und keine Produktiv-Testbuchungen.
- Lohnabrechnung ist ein getrenntes Feature. Dieses Redesign behauptet keine
  fertige oder zertifizierte Lohnabrechnung und ergänzt keine funktionslosen Menüpunkte.
- Ein technischer Build ersetzt keine visuelle Browser-Abnahme.

## Abnahme

Verifiziert: TypeScript ohne Fehler, oxlint ohne Meldung, Vite-Produktionsbuild
mit 52 Modulen. Der HTTP-Smoke-Test lieferte HTML, CSS, JavaScript, Wortmarke,
Manrope und IBM Plex Sans jeweils mit Status 200. 96 Backend-Tests blieben grün.
Eine visuelle Browser-Abnahme wurde nicht durchgeführt und bleibt offen.

Desktop-Erweiterung verifiziert: TypeScript ohne Fehler, oxlint ohne Meldung,
Vite-Produktionsbuild mit 56 Modulen. Backend ist von dieser Änderung nicht
betroffen. Eine visuelle Browser-Abnahme der Desktop-Sidebar bei ≥1024px
wurde nicht durchgeführt (Chrome-Anbindung war in dieser Session nicht
verbunden) und bleibt ebenfalls offen.
