# Spec: Suche und Schnellaktionen (Strg+K) und Listenwerkzeuge

Status: GEBAUT (Branch `feature/datenumzug`, Phase 3 des Plans Datenumzug).

## Problem

Wer viele Kunden, Rechnungen und Belege hat, musste durch Listen scrollen oder wissen, in
welchem Menü etwas liegt. Nur die Kontakte-Seite hatte eine Suche.

## Verhalten

**Befehlspalette** (Strg+K bzw. Cmd+K, Suchknopf oben in der Seitenleiste, Lupe in der
Kopfzeile auf dem Handy)

- Ohne Eingabe zeigt sie Schnellaktionen: Neue Rechnung, Beleg hochladen, Kontakt anlegen,
  Daten importieren (nur Inhaber), Kontoauszug importieren. Eine Schnellaktion öffnet nur die
  Seite oder das leere Formular, sie legt nichts an und versendet nichts.
- Ab 2 Zeichen wird der Datenbestand durchsucht (Kontakte, Rechnungen, Angebote, Belege,
  Produkte). Zusätzlich findet sie Seiten der Navigation ("EÜR", "Mahnungen") und
  Schnellaktionen per Stichwort. Mehrere Wörter müssen alle vorkommen.
- Ein Treffer öffnet die Seite und springt zum Datensatz: Kontakte und Produkte werden
  aufgeklappt, Rechnungen, Angebote und Belege in die Mitte gescrollt und kurz farbig markiert.
  Archivierte Kontakte werden gefunden (Kennzeichnung "archiviert") und im Archiv-Reiter geöffnet.
- Bedienung: Pfeiltasten, Enter, Esc. Die Eingabe wird 250 ms entprellt, veraltete Anfragen
  werden abgebrochen. Das alte Ergebnis bleibt gedimmt stehen, bis das neue da ist. Esc gibt
  den Fokus an die vorherige Stelle zurück.
- Pro Gruppe höchstens 5 Treffer, darunter "+ N weitere Treffer. Fasse den Suchbegriff genauer."

**Backend** (`POST /suche`, `app/suche/`)

- POST mit JSON-Body statt GET, damit Suchbegriffe (Kundennamen, Beträge) nicht in Zugriffs- und
  Proxy-Logs landen. Suchanfragen werden nicht protokolliert. Anmeldung mit MFA nötig, alles
  nach Mandant gefiltert.
- Felder: Kontakte (Name, Ansprechpartner, Kundennummer, E-Mail, Ort), Rechnungen (Nummer,
  Kunde, Betreff, Referenznummer, Betrag), Angebote (Nummer, Kunde, Betrag), Belege (Anbieter,
  Rechnungsnummer, Betrag), Produkte (Bezeichnung, Artikelnummer, Beschreibung).
- Rangfolge: Feldanfang, dann Wortanfang, dann enthalten. Gleicher Rang: neueste zuerst.
  Beträge zählen nur vom Zahlenanfang her ("119" findet 119,00 und 1.190,00, nicht 2.119,00)
  und in den Schreibweisen 1.240,00, 1240,00 und 1240.00.
- Groß-/Kleinschreibung, Akzente und Umlaut-Punkte werden ignoriert ("müller" findet "Müller").

**Listenwerkzeuge** (`ListenWerkzeug`, `useListenFilter`)

- Rechnungen, Angebote, Belege und Produkte bekommen Filter-Reiter mit Anzahl, ein Suchfeld und
  eine Sortierung. Das arbeitet auf den schon geladenen Daten, es gibt keine Serveranfrage. Die
  Zahl an jedem Reiter folgt der aktuellen Suche. Lässt die Auswahl nichts übrig, steht dort
  "Keine Treffer" mit Zurücksetzen statt der Einstiegsseite "noch keine Rechnungen".
- Rechnungen filtern nach dem Anzeigestatus (Entwurf, Offen, Überfällig, Bezahlt, Storniert),
  genau wie die Statusanzeige in der Liste. Die Palette nutzt dieselbe Unterscheidung.
- Die Kontakte-Seite hat ihre Reiter und Suche aus Phase 1 und nutzt die neue Komponente nicht.

## Annahmen, die ich getroffen habe

- **Grenze von 5000 Zeilen je Typ.** Die Felder sind verschlüsselt, die Datenbank kann nicht
  suchen. Geladen werden die 5000 neuesten Zeilen je Typ, verglichen wird in Python. Wird die
  Grenze erreicht, sagt die Palette es ("Nicht alle Daten durchsucht") statt Treffer zu
  verschweigen. Einen Suchindex (etwa mit Blind-Index oder Trigrammen) habe ich bewusst nicht
  gebaut: Er würde Informationen über die verschlüsselten Werte preisgeben und braucht eine
  eigene Sicherheitsentscheidung.
- **Messwerte (Wegwerf-SQLite, lokal, eine Anfrage, Median):**
  - Typischer Kleinbetrieb (400 Kontakte, 1500 Rechnungen, 300 Angebote, 1000 Belege, 150
    Produkte): etwa 115 bis 150 ms. Das Ziel von unter 300 ms ist erreicht.
  - Extremfall (je 5000 Zeilen, 25 000 Zeilen insgesamt): etwa 0,95 s. **Das Ziel wird dort
    verfehlt.** Vor der Optimierung waren es etwa 1,45 s. Der Rest ist im Kern die Entschlüsselung
    von rund 85 000 Einzelwerten (je Wert eigener Schlüssel, zwei AES-GCM-Vorgänge).
  - Gemessen auf SQLite, nicht auf Postgres mit Netzwerk. Der Wert auf dem Server kann abweichen.
  - Die Messung lief mit einer Anfrage zur Zeit. Mehrere gleichzeitige Suchen mehrerer Nutzer
    habe ich nicht gemessen.
- **Änderung an der Verschlüsselung (`app/core/key_management.py`).** Die Ableitung des
  Schlüssels (HKDF) lief bei jedem entschlüsselten Wert neu, obwohl das Ergebnis nur von
  Hauptschlüssel und Zweck abhängt. Sie ist jetzt zwischengespeichert (`lru_cache`). Das
  Verhalten ist gleich, die Krypto- und Rotationstests sind grün. Es beschleunigt auch alle
  Listenseiten. Abgeleitete Schlüssel liegen dadurch im Arbeitsspeicher des Prozesses. Die
  Hauptschlüssel lagen dort schon.
- **Nicht durchsucht:** Ausgaben ohne Beleg (aus wiederkehrenden Ausgaben), Rechnungspositionen,
  Kategorien gebuchter Belege, Mahnungen, Lohndaten.
- **Kundennamen bei Rechnungen und Angeboten** kommen aus den 5000 neuesten Kontakten. Bei mehr
  Kontakten fehlt für ältere Kontakte der Name im Treffer.
- **"mueller" findet nicht "Müller".** Umlaute werden zu a/o/u gefaltet, ue/ae/oe aber nicht
  (sonst gäbe es mehr falsche Treffer). Wer "Mueller" eintippt, muss "muller" oder "müller"
  schreiben.
- **Die Seitenliste der Palette** kommt aus der Navigationsstruktur. Punkte mit "Bald
  verfügbar" erscheinen nicht.
- **Zustand "überfällig"** wird wie in der Rechnungsliste aus dem heutigen Datum berechnet.

## Geprüft und nicht geprüft

- Backend: 16 Tests in `tests/test_suche.py` (Gruppen, Rang, Beträge, Umlaute, Archiv,
  Mandantentrennung, Limits, Obergrenze, nur POST, Status überfällig/bezahlt).
- Oberfläche: im echten Chromium (headless, lokal) gegen simulierte Serverantworten
  durchgespielt, auf 1280 px und 390 px Breite: Tastatur, Sprung zu allen fünf Datensatztypen,
  archivierter Kontakt, Fehler- und Leerzustände, Listenfilter und Sortierung, kein
  horizontales Scrollen. Die Chrome-Erweiterung war nicht erreichbar.
- **Nicht geprüft:** gegen das echte Backend im Browser, Firefox und Safari, Bedienung mit
  Screenreader (ARIA-Combobox-Muster ist umgesetzt, aber nicht mit einem echten Screenreader
  getestet), Tablet-Breiten dazwischen.
