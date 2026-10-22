# Spec: Kontoauszug-Import mit Zahlungsabgleich

Status: GEBAUT (Branch `feature/belege-bank`, Phase C des Feature-Plans Belege und Bank).

## Problem

Rechnungen als bezahlt markieren und Ausgaben ihrem Beleg zuordnen kostet jeden Monat Zeit
und ist fehleranfällig. Eine Live-Bankanbindung (finAPI, PSD2) braucht Lizenz, kostet Geld und
verändert die Datenschutz-Lage. Ein Dateiimport löst den Alltagsfall ohne das.

## Verhalten

- **Konten:** Der Nutzer legt ein Bankkonto an (Bezeichnung, IBAN optional).
- **Import:** CAMT.053 (XML) oder CSV, erkannt am Inhalt, bis 10 MB (`bank_max_bytes`).
  - CAMT.053 wird namespace-unabhängig gelesen (verschiedene Versionen). Nur gebuchte
    Einträge (`BOOK`). Sammelbuchungen mit je eigenem Betrag werden zu einzelnen Umsätzen.
    Die IBAN der Datei muss zum Konto passen, ein Konto ohne IBAN übernimmt sie.
  - CSV: Kodierung (UTF-8, Windows-1252) und Trennzeichen werden erkannt. Ein
    **Spaltenprofil** (Datum, Datumsformat, Betrag oder Soll/Haben, Name, IBAN,
    Verwendungszweck, Zahlenformat) wird vorgeschlagen, vom Nutzer geprüft und je Konto
    gemerkt. Fehlerhafte Zeilen brechen den Import ab (mit Zeilennummern), nichts wird still
    übersprungen. Nur Euro.
- **Doppelte vermeiden:** Hash aus Konto, Datum, Betrag, Gegenpartei, Zweck und der laufenden
  Nummer gleicher Zeilen in der Datei. Ein erneuter Import überlappender Zeiträume legt
  nichts doppelt an, zwei echte gleiche Zahlungen am selben Tag bleiben getrennt.
- **Vorschläge** (`app/bank/matching.py`, reine Funktionen):
  - Eingang gegen offene finale Rechnungen: Betrag gleich (0.5), Rechnungsnummer im
    Verwendungszweck (0.45, tolerant bei Trennzeichen), Namensähnlichkeit (bis 0.15).
    **Sicher** nur bei Betrag und Nummer. Mehrere gleich gute Rechnungen: nie sicher, die
    älteste wird vorgeschlagen. Nummer passt, Betrag nicht: Vorschlag mit Hinweis
    "Betrag weicht ab", nie sicher.
  - Ausgang gegen noch nicht gebuchte Belege und gebuchte Ausgaben ohne Zahlung: Betrag gleich
    und (Name ähnlich oder Datum höchstens 5 Tage entfernt). Nie sicher.
  - Jeder Vorschlag nennt seine Gründe im Klartext.
- **Zuordnen:** immer nur auf Bestätigung, einzeln, über "Andere wählen" oder gesammelt für
  sichere Treffer. Gesammeltes Bestätigen prüft jeden Vorschlag neu und überspringt alles
  Unsichere mit Begründung.
  - Rechnung: wird mit `zahlungen.markiere_rechnung_bezahlt` (`bezahlt_am` = Buchungsdatum)
    bezahlt. Der Betrag muss exakt passen.
    Das lässt sich nicht aufheben (Bezahlbuchungen werden nicht zurückgenommen).
  - Beleg: Das Zahlungsdatum wird im Bestätigungsformular vorbelegt. Wird der Beleg
    gebucht, zeigt die Zuordnung auf die neue Ausgabe, wird er gelöscht, ist die Zahlung wieder
    offen.
  - Ausgabe: reine Verknüpfung, die unveränderbare Ausgabe bleibt unberührt.
- **Beleg fehlt:** Offene Abgänge ohne Zuordnung. Ignorieren mit Grund (z. B. Bankgebühr,
  Privatentnahme) und "Wieder öffnen" sind möglich.
- Alle Änderungen stehen im Audit-Log (`bank_import`, `bank_zuordnung`,
  `bank_zuordnung_aufgehoben`, `bank_ignoriert`).
- Kein Tarif-Gate mehr (früher nur Pro und Business).

## Technik

- Migration `0031` (`bankkonten`, `bankimporte`, `bankumsaetze`, Row-Level-Security).
- Alle personenbezogenen Felder sind verschlüsselt (`EncryptedText`/`EncryptedDecimal`), das
  Suchbare nur als Blind-Index (IBAN, Duplikat-Hash). Die Originaldatei liegt verschlüsselt in
  `bank_storage_dir` (Zweck `bank-file`) und ist in die Schlüsselrotation aufgenommen.
- Datenexport enthält Konten, Importe und Umsätze (ohne interne Hashes).
- Oberfläche: Seite "Kontoauszug" (Bank, im Menü und unter Mehr).

## Annahmen, die ich getroffen habe

- **Nur synthetische Dateien getestet.** Echte Bankexporte weichen oft ab (zusätzliche
  Kopfzeilen, ungewöhnliche Datums- und Zahlenformate, mehrzeilige Felder, Salden). Die
  CSV-Fixtures im Stil verbreiteter Exporte sind nachgebaut, nicht von einer echten Bank.
  Anonymisierte echte Exporte werden als Fixtures benötigt.
- **Stornoeinträge (`RvslInd`):** Ich behandle eine Rückbuchung als Gegenrichtung zur
  gemeldeten Soll/Haben-Kennung. Das ist meine Lesart der ISO-20022-Regel und nicht an einer
  echten Datei geprüft.
- **Ein Format je Konto:** Dasselbe Konto einmal als CAMT und einmal als CSV zu importieren
  erzeugt Doppelte, weil sich die Felder unterscheiden.
- **Nur exakte Beträge.** Teilzahlungen, Skonto, Überzahlung und Sammelzahlungen werden nicht
  gematcht. Die Zuordnung zu einer Rechnung mit abweichendem Betrag wird abgelehnt.
- **Beleg-Vorschläge nutzen nur Betrag, Name und Datum.** Die Schwellen (Name ab 0.6, Datum
  5 Tage) sind Schätzwerte ohne Praxisdaten.
- Keine Verwaltung von Konten (umbenennen, löschen) und kein Löschen einzelner Importe in v1.
