# Spec: Gemeinsamer Erfassungsweg, Upload-Härtung, Kategorien lernen

Status: GEBAUT (Branch `feature/belege-bank`). Teil des Feature-Plans Belege und Bank
(Phase 0 und A).

## Problem

- Bei wiederkehrenden Anbietern blieb die Kategorie "unklar", obwohl der Nutzer sie schon
  mehrfach bestätigt hatte.
- Der Beleg-Upload vertraute dem vom Client gemeldeten Dateityp und hatte kein
  Größenlimit.

## Phase 0: Erfassungsweg und Härtung

- `app/receipts/service.py::erfasse_beleg` ist der einzige Weg, einen Beleg anzulegen
  (Mandant sperren, Monatslimit prüfen, Typ erkennen, Duplikat, Speichern, Extraktion,
  Audit). Der HTTP-Upload nutzt ihn, Kamera und E-Mail-Eingang sollen ihn später nutzen.
- Dateityp kommt aus dem Inhalt (`erkenne_dateityp`: PDF, JPEG, PNG, WebP, XML). Der
  Client-Header wird nur noch in der Fehlermeldung angezeigt.
- `receipt_max_bytes` (15 MB) begrenzt den Upload, HTTP 413 bei Überschreitung. Pillow
  `MAX_IMAGE_PIXELS` (60 Mio.) schützt vor Dekompressionsbomben.
- `app/core/xml_safe.py::parse_xml_sicher` liest XML aus unsicherer Quelle: kein DOCTYPE, keine
  Entitäten, kein Netzwerk, Größenlimit. Wird von E-Rechnung und Kontoauszug genutzt.

## Phase A: Kategorien lernen

- Historie = die letzten 500 gebuchten `Ausgabe`-Zeilen des Mandanten (verschlüsselte
  Felder, deshalb Gruppierung in Python, `app/receipts/lernen.py`).
- Anbieter-Vergleich über einen normalisierten Schlüssel (klein, ohne Rechtsform und
  Satzzeichen). Treffer bei Gleichheit oder wenn der kürzere Name (mindestens 5 Zeichen) als
  ganzes Wort im längeren vorkommt. "Vodafone GmbH" trifft "Vodafone Deutschland GmbH",
  "Bahn GmbH" trifft nicht "Deutsche Bahn AG".
- Vorschlag = häufigste Kombination aus Kategorie und Konto. Konfidenz 0.85 (eine Buchung),
  0.9 (zwei), 0.95 (ab drei). Bei widersprüchlicher Historie nur bei klarer Mehrheit
  (mindestens 2 und mehr als jede andere Kombination), Konfidenz 0.65. Sonst kein Vorschlag.
- USt-Satz wird nur vorgeschlagen, wenn alle passenden Buchungen denselben Einzelsatz haben
  und der OCR-Satz unklar ist.
- Ein gelernter Wert ersetzt die OCR-Heuristik nur, wenn er sicherer ist. Der Anbieter des
  Belegs muss selbst sicher erkannt sein.
- Anwendung beim Lesen (`effektive_vorschlaege`), nicht beim Speichern: Auch bereits
  hochgeladene, offene Belege profitieren sofort. `bestaetige_beleg` nutzt dieselben Werte
  als Standard. Das gelernte Konto gilt nur, wenn auch die gelernte Kategorie übernommen wird.
- `GET /belege/vorschlag?anbieter=` liefert den Vorschlag für das Bestätigungsformular,
  das ihn beim Verlassen des Anbieter-Felds in leere Felder einträgt.
- Kein Tarif-Gate mehr (früher nur Business, wie die übrigen Buchungsvorschläge).

## Annahmen, die ich getroffen habe

- 500 Buchungen reichen als Gedächtnis und halten die Abfrage klein. Bei sehr großen
  Beständen könnte ein Blind-Index auf den Anbieter nötig werden.
- Die Mehrheitsregel und die Konfidenzstufen sind Schätzwerte ohne Praxisdaten.
- Falsch bestätigte Buchungen werden mitgelernt. Gegenmaßnahme: Die Begründung nennt immer
  die Zahl der Buchungen, und der Nutzer bestätigt jeden Beleg selbst.
- Gelernte Vorschläge sind Hinweise, keine Steuerberatung. Die Konten sind weiter nicht
  steuerberatergeprüft.
