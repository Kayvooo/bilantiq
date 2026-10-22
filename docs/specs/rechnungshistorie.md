# Spec: Rechnungshistorie, PDF-Archiv und offene Posten (Rechnungen aus dem alten Programm)

Status: GEBAUT (Branch `feature/datenumzug`, Phase 4 des Plans Datenumzug).

## Problem

Wer von einem anderen Programm kommt, lässt dort Rechnungen zurück: bezahlte, die man nachweisen
muss, und offene, auf deren Geld man noch wartet. Ohne Übernahme muss er zwei Programme parallel
führen, bis alles bezahlt ist, und die alten PDFs liegen irgendwo.

## Grundsatz

Eine **Altrechnung ist keine Bilantiq-Rechnung.** Sie bekommt keine Nummer aus dem Bilantiq-Nummernkreis,
wird nie neu als PDF erzeugt und ist unveränderbar (GoBD). Geändert wird nur, was nach dem Umzug
geschieht: Zahlungen, die in Bilantiq erfasst werden.

## Verhalten

**Import der Rechnungsliste** (Stammdaten-Ziel `rechnungen`, nur Inhaber, gleicher Assistent wie bei
Kontakten: Datei, Spalten, Prüfen, Fertig)

- Felder: Rechnungsnummer und -datum (Pflicht), Kunde (Name oder Kundennummer), Fälligkeit, Netto, USt-Betrag,
  Brutto, USt-Satz, Netto je Steuersatz (19, 7, 0 %), offener Betrag, bezahlt am, Status. Die Spaltenvorschläge
  unterscheiden eine Spalte „USt“ nach den Beispielwerten: nur 0, 5, 7, 16 oder 19 gelten als Satz, alles andere als Betrag.
- **Steuersatz wird nicht berechnet, nur geprüft:** zuerst Netto je Steuersatz, dann ein angegebener Satz (gegen den
  Brutto-Betrag auf den Cent geprüft), sonst abgeleitet aus Netto und Brutto (nur 19, 7, 0, ersatzweise 16 und 5 %).
  Lässt sich der Satz nicht eindeutig bestimmen (gemischte Sätze ohne Aufteilung), wird die Zeile **abgelehnt** statt
  geraten.
- **Was als offen gilt:** ein angegebener offener Betrag, sonst 0 bei Status bezahlt/storniert oder wenn „bezahlt am“
  steht, sonst der ganze Bruttobetrag. Widersprüche (bezahlt, aber offener Betrag) und unbekannte Status sind Fehler,
  weil davon abhängt, was als Forderung zählt. Fehlt die Fälligkeit, gilt Rechnungsdatum plus gewählte Tage, mit Hinweis.
- Abgelehnt werden: negative Beträge (Gutschriften), Entwürfe, Nullbeträge, Rechnungsdatum in der Zukunft, eine Nummer,
  die es schon als Bilantiq-Rechnung gibt, Kundennummer mit anderem Namen. Schon vorhandene Nummern (auch in anderer
  Schreibweise, „RE 2024 1“ = „RE-2024-1“) und doppelte Zeilen werden übersprungen.
- Kunden werden über Kundennummer, sonst über den genauen Namen zugeordnet. Optional werden fehlende Kunden als
  Kontakt angelegt.
- Die Quelldatei der Rechnungsliste bleibt **verschlüsselt** als Nachweis der Übernahme erhalten.
- Rückgängig: entfernt die angelegten Altrechnungen ohne erfasste Zahlung und ohne PDF und die angelegten Kunden,
  die nirgends verwendet werden.

**Archiv und Alltag** (`/altrechnungen`, Rechnungsseite, Reiter „Aus dem alten Programm“)

- Liste mit Filter (offen, überfällig, bezahlt), Suche, Sortierung. Eine Altrechnung hat den Status offen, überfällig
  oder bezahlt (auch: schon im alten Programm bezahlt, dann mit Vermerk).
- **Zahlung erfassen:** Datum (nicht in der Zukunft) und Betrag, Standard ist der ganze offene Betrag. Ein kleinerer
  Betrag ist eine Teilzahlung, der Rest bleibt offen. Mehr als offen ist, wird abgelehnt. Wie bei Bilantiq-Rechnungen lässt
  sich eine Zahlung nicht zurücknehmen.
- **PDF-Archiv:** mehrere PDFs auf einmal (bis 20 je Anfrage, je 15 MB). Zugeordnet wird über die Rechnungsnummer im
  Dateinamen („RE-2024-0001.pdf“, „Rechnung RE 2024 0001 Müller.pdf“). Eindeutig heißt: genau eine Nummer, nicht von
  weiteren Ziffern oder Buchstaben umgeben („RE-2024-1“ steckt nicht in „RE-2024-10“), die längste passende gewinnt, kurze
  Nummern (unter 4 Zeichen) nur als ganzer Name. Alles andere wird mit Grund gezeigt und lässt sich von Hand zuordnen.
  Gleiche Dateien und Rechnungen, die schon ein PDF haben, werden abgelehnt. Die PDFs liegen verschlüsselt
  (`altrechnung-file`). **Es gibt kein Löschen und kein Ersetzen.** Ablegen und Ansehen sind ohne Tarifbindung möglich.
- **Kontakt:** Abschnitt „Rechnungshistorie“ mit Bilantiq- und Altrechnungen, Umsatz (Brutto, auch aus der Zeit im alten
  Programm) und offenem Betrag. Ein Kontakt mit Altrechnungen lässt sich nur archivieren, nicht löschen.
- **Suche:** eigene Gruppe „Rechnungen aus dem Altsystem“, die in den Reiter springt.

## Wie Altrechnungen in die Auswertungen eingehen

| Auswertung | Regel |
|---|---|
| Einnahmen-Überschuss-Rechnung | nur in Bilantiq erfasste Zahlungen, netto, im Jahr des Zahlungsdatums |
| Umsatzsteuer-Voranmeldung | dieselben Zahlungen, im Zeitraum des Zahlungsdatums, Umsatzsteuer **anteilig nach gezahltem Betrag je Steuersatz** (Ist-Versteuerung) |
| Dashboard | Einnahmen und Umsatz wie EÜR, offene und fällige Forderungen enthalten offene Altrechnungen, Kundenumsatz enthält erfasste Zahlungen |
| Cashflow-Prognose | offene Altrechnungen nach Fälligkeit mit dem Restbetrag |
| DATEV-Export, SuSa, BWA | eine Buchung je Zahlung und Steuersatz, Erlöskonto nach Satz, die alte Rechnungsnummer im Belegfeld |
| Bankabgleich | offene Altrechnungen sind Kandidaten (Restbetrag, Nummer im Verwendungszweck, Name, IBAN), eine bestätigte Zuordnung erfasst die Zahlung mit dem Buchungsdatum |

**Was im alten Programm bezahlt wurde, zählt nie.** Das steht dort in den Büchern, sonst würde es doppelt gezählt.

## Annahmen, die ich getroffen habe

- **Zahlungen als eigene Tabelle** statt eines einzelnen „bezahlt“-Felds (so war es im Plan skizziert). Grund: Teilzahlungen
  und die Zuordnung zum Zeitraum des Zahlungsdatums für EÜR und Umsatzsteuer. Ein Kennzeichen `war_offen` im Klartext sorgt
  dafür, dass Berichte nur die wenigen beim Umzug offenen Rechnungen laden und nicht das ganze Archiv entschlüsseln.
- **Nur Euro, keine Gutschriften, keine Teil-Stornos.** Status „storniert“ wird als erledigt archiviert (offener Betrag 0),
  der Bruttobetrag bleibt dabei im Umsatz der Kontakt-Historie stehen.
- **Es gibt keinen „Rest ausbuchen“.** Zahlt ein Kunde weniger (Skonto, Kulanz), bleibt die Differenz als offene Forderung
  stehen. Eine Funktion, den Rest abzuschreiben, fehlt.
- **Rückdatierte Zahlungen** zählen im Jahr ihres Datums. Wer eine Zahlung aus der Zeit im alten Programm hier erfasst, kann
  sie doppelt zählen (alte Bücher plus Bilantiq). Das wird nicht geprüft.
- **Satz 16 % und 5 % (zweites Halbjahr 2020)** sind für das Archiv zugelassen. Zahlungen darauf würden in der
  Umsatzsteuer-Voranmeldung als „sonstige“ ohne Umsatzsteuer erscheinen und im DATEV-Export auf das Konto für 0 % laufen.
  Das ist für Zahlungen ab 2026 kaum denkbar, aber nicht abgesichert.
- **Mahnungen, E-Mail-Versand und Zahllink für Altrechnungen gibt es nicht** (Plan: später).
- **Nummernkreis ist noch nicht fortgesetzt.** Der Import lehnt Nummern ab, die es schon als Bilantiq-Rechnung gibt. Umgekehrt
  kann Bilantiq heute noch eine neue Nummer vergeben, die es im alten Programm schon gab (zum Beispiel „RE-2026-0001“). Das
  Fortsetzen des Nummernkreises und die Absicherung beim Finalisieren sind **Phase 5**. Bis dahin sollte man alte Rechnungen
  des laufenden Jahres nicht mit gleichem Nummernformat parallel zu neuen Bilantiq-Rechnungen führen.
- **PDFs werden nur an der Dateisignatur (`%PDF-`) erkannt.** Kein Virenscan, keine PDF/A-Prüfung, kein Abgleich von Inhalt
  und Rechnungsnummer. Die Zuordnung über den Dateinamen ist eine Heuristik mit den oben genannten Regeln.
- **Aufbewahrung:** Es gibt keine Funktion zum Löschen von Altrechnungs-PDFs und keine Fristprüfung. Beim Löschen des
  Kontos bleiben Geschäftsdaten wie bei allen anderen Belegen unter der Aufbewahrungspflicht (der Nutzer wird anonymisiert).
- **DATEV-Buchung** für Zahlungen auf Altrechnungen ist nicht gegen echtes DATEV getestet und sollte mit dem Steuerberater
  abgestimmt werden.
- **Bankabgleich:** Eine Bankzahlung darf eine Teilzahlung auf eine Altrechnung sein (bei Bilantiq-Rechnungen verlangt der
  Abgleich weiterhin den vollen Betrag). Das ist ein bewusster Unterschied.
- **Nicht gemessen:** Laufzeit der Berichte bei sehr großen Archiven (Zehntausende Altrechnungen mit vielen Zahlungen).
- **Nicht mit echten Exportdateien getestet:** lexoffice, sevdesk, DATEV oder Excel-Rechnungslisten. Die Spaltenvorschläge sind
  mit selbst gebauten Dateien geprüft.

## Nebenbefund (inzwischen behoben)

Die Schlüsselrotation (`scripts/rotate_encryption.py`) kannte **42 ältere verschlüsselte Spalten nicht** (zum Beispiel alle
Rechnungs- und Angebotsbeträge, Belegbeträge, Lohnentwürfe). Bei einer Rotation wären sie mit dem alten Schlüssel
verschlüsselt geblieben, der sich dann nicht mehr hätte entfernen lassen. Behoben im Commit zur Rotation: Das Skript leitet
die Spalten jetzt aus den Modellen ab (jede verschlüsselte Spalte kennt ihren Verwendungszweck), statt eine Liste von Hand
zu pflegen. Neu ist außerdem `python -m scripts.rotate_encryption --pruefen`, das nur liest und meldet, ob noch Werte auf einem
anderen als dem aktiven Schlüssel liegen. Siehe `tests/test_schluesselrotation.py`.

## Geprüft und nicht geprüft

- Backend: 19 Tests für Steuerlogik und Import, 15 für Liste, Zahlungen, PDF-Archiv, Historie und Export, 8 für EÜR, UStVA,
  Dashboard, Cashflow, DATEV und Bankabgleich, dazu 1 für die Suche.
- Oberfläche: im echten Chromium gegen einen simulierten Server durchgespielt (Reiter, Filter, Zahlung mit zu hohem Betrag und
  Teilzahlung, PDF-Zuordnung automatisch und von Hand, Importassistent mit Probelauf, Kontakt-Historie, Suche mit Sprung), auf
  1280, 390 und 320 px Breite ohne horizontales Überlaufen.
- **Nicht geprüft:** das echte Backend im Browser, Firefox und Safari, Screenreader, echte Exportdateien anderer Programme, die
  Berichte mit großen Beständen.
