# Spec: Stammdaten importieren und exportieren (Kontakte, Produkte)

Status: GEBAUT (Branch `feature/datenumzug`, Phase 2 des Plans Datenumzug).

## Problem

Wer von einem anderen Programm kommt, musste jeden Kunden und jedes Produkt abtippen. Und wer
Bilantiq verlassen will, konnte Stammdaten nur als DSGVO-JSON exportieren.

## Verhalten

- **Dateien:** CSV (Kodierung und Trennzeichen werden erkannt) und Excel `.xlsx`, erkannt am
  Inhalt, bis 10 MB und 20 000 Zeilen. Altes `.xls`, passwortgeschützte Mappen, ODS und PDF
  werden mit klarer Meldung abgelehnt. Bei mehreren Tabellenblättern ist das Blatt wählbar.
- **Spaltenzuordnung:** Bilantiq schlägt für jedes Feld eine Spalte vor (exakte Überschrift,
  danach "enthält", allgemeine Wörter wie "Nummer", "Land" oder "Preis" nur exakt). Der Nutzer
  bestätigt oder ändert. Jede Spalte gehört höchstens einem Feld.
- **Umwandlung:** Name aus Firma, sonst aus Vor- und Nachname (dann Privatkunde). Hausnummer
  wird an die Straße angehängt. Länder als Name oder Kürzel. Vierstellige deutsche PLZ bekommen
  die von Excel verlorene führende Null zurück. Ja/Nein in vielen Schreibweisen. Zahlen im
  gewählten Format, eindeutige Werte im anderen Format ("90.00" bei Dezimalkomma) werden
  trotzdem richtig gelesen. Produkte: Brutto- statt Nettopreis möglich, USt-Satz nur 0, 7,
  19 %, ohne Angabe gilt der gewählte Standard-Satz, ohne Preis 0,00 € mit Hinweis.
- **Probelauf:** Zeigt je Zeile neu, wird ergänzt, schon vorhanden, doppelt in der Datei oder
  Fehler, dazu die ersten neuen Datensätze so, wie sie angelegt würden. Es wird nichts
  gespeichert.
- **Fehler und Hinweise:** Fehler im Pflichtfeld (Name, Bezeichnung) oder ein Konflikt sperren
  die Zeile. Ungültige optionale Werte (E-Mail, IBAN, Land, ...) lassen nur das Feld leer und
  erscheinen als Hinweis. Gesperrte Zeilen blockieren den Import, bis der Nutzer ausdrücklich
  "ohne die fehlerhaften Zeilen" wählt. Die Fehlerliste gibt es als CSV (Originalzeile plus
  Spalte "Fehler").
- **Doppelte:** Kontakte nach Kundennummer, USt-IdNr., E-Mail (nur bei ähnlichem Namen), Name
  plus PLZ. Produkte nach Artikelnummer, Bezeichnung. Gleiche Nummer bei anderem Namen ist ein
  Fehler (z. B. Nummernkreise zweier Systeme überschneiden sich). Standard: überspringen.
  "Leere Felder ergänzen" füllt nur leere Felder, überschreibt nie etwas; Kunde plus Lieferant
  wird "beide".
- **Rückgängig:** Ein Import lässt sich einmal rückgängig machen. Gelöscht werden nur angelegte
  Datensätze, die noch nirgends verwendet werden (Kontakte ohne Dokumente, Produkte ohne
  Lagerbewegung). Ergänzte Felder bleiben.
- **Export:** CSV (UTF-8 mit BOM, Semikolon) oder Excel. Spaltennamen wie die Importfelder,
  Kontakte zusätzlich mit "Archiviert". Ein Export lässt sich unverändert wieder importieren.
  Importvorlage = leerer Export plus Beispielzeile.
- **Formel-Injection:** In CSV werden Zellen mit `=`, `+`, `-`, `@`, Tab, CR am Anfang mit `'`
  entschärft (beim Reimport wird genau dieses Zeichen wieder entfernt). In Excel werden Texte
  ausdrücklich als Text geschrieben.
- **Rechte:** Nur der Inhaber (`require_owner`), für Mitglieder sind die Knöpfe ausgeblendet.
  Keine Tarifbindung.
- **Audit:** `stammdaten_import`, `stammdaten_import_rueckgaengig`, `stammdaten_export`.

## Technik

- `app/core/tabelle.py`: gemeinsamer Leser für CSV und XLSX (auch der Bankimport nutzt ihn).
  XLSX über openpyxl `read_only`, `data_only` (Formeln werden nie ausgewertet), defusedxml
  installiert. Vor dem Öffnen: höchstens 1000 Archiveinträge, 50 MB entpackt, Packrate je
  Eintrag über 1 MB höchstens 200.
- `app/stammdaten/`: `felder.py` (Felder, Labels, Synonyme), `werte.py` (Umwandlung),
  `service.py` (Probelauf, Import, Rückgängig), `export.py`, `routes.py`.
- Migration `0033`: Tabelle `datenimporte` (RLS), `import_id` an `kontakte` und `produkte`.
  Die Quelldatei wird nicht gespeichert, nur Name (verschlüsselt), Hash und Zähler.
- Endpunkte unter `/stammdaten`: `{ziel}/import/vorschau`, `{ziel}/import/pruefen`,
  `{ziel}/import/fehlerliste`, `{ziel}/import`, `importe`, `importe/{id}/rueckgaengig`,
  `{ziel}/export?format=csv|xlsx`, `{ziel}/vorlage?format=`.
- Oberfläche: `features/stammdaten/ImportAssistent.tsx` (Datei, Spalten, Prüfen, Fertig) und
  `StammdatenAktionen.tsx` auf den Seiten Kontakte und Produkte.

## Annahmen, die ich getroffen habe

- **Nur mit selbst gebauten Dateien getestet.** Die Synonyme sind aus typischen
  Spaltennamen abgeleitet, nicht aus echten lexoffice- oder sevdesk-Exporten.
- Der Bestand wird zum Vergleich komplett entschlüsselt. Für einige tausend Kontakte ist das
  schnell genug, für sehr große Bestände nicht gemessen.
- E-Mail-Gleichheit allein reicht nicht für "vorhanden" (gemeinsame Adressen wie info@ einer
  Gruppe), es braucht zusätzlich einen ähnlichen Namen.
- Die Oberfläche ist mangels Browserzugriff in dieser Sitzung nur per Typprüfung und Build
  geprüft, nicht im Browser.
