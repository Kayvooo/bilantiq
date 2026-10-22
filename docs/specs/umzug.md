# Spec: Umzugsassistent und Nummernkreis fortsetzen

Status: GEBAUT (Branch `feature/datenumzug`, Phase 5 des Plans Datenumzug).

## Problem

Wer mitten im Jahr von einem anderen Programm kommt, hat dort schon Rechnungsnummern vergeben, zum Beispiel
`RE-2026-0001` bis `RE-2026-0150`. Bilantiq vergibt Nummern nach `RE-JJJJ-NNNN` und finge wieder bei 1 an: Dieselbe
Nummer gäbe es zweimal. § 14 UStG verlangt eindeutige Rechnungsnummern. Außerdem fehlt dem Nutzer ein Überblick, was beim
Wechsel alles zu tun ist.

## Verhalten

**Nummernkreis** (`/einstellungen/nummernkreis`, Einstellungen, Buchhaltung, und im Umzugsassistenten)

- Zeigt die nächste Rechnungsnummer, die höchste in Bilantiq vergebene und die höchste aus dem Altsystem. Als Nummer des
  Altsystems zählt eine importierte Rechnung im Format `RE-<laufendes Jahr>-N` (Trennzeichen und führende Nullen egal: „RE 2026 150“
  ist 150). Ist die nächste Bilantiq-Nummer nicht größer als die höchste alte, warnt der Bereich und schlägt die erste freie vor.
- **Setzen** darf nur der Inhaber, **nur nach oben** und **nur über der höchsten schon vergebenen** Nummer (auch der aus dem
  Altsystem). Der Wert gilt für das laufende Jahr. Jede Änderung steht im Änderungsprotokoll (`nummernkreis_gesetzt`). Der Server
  prüft und erklärt Verstöße im Klartext („Im alten Programm gibt es schon Rechnungen bis …“).
- Mitglieder sehen den Stand, ändern können sie ihn nicht.

**Letzte Absicherung bei der Vergabe:** Beim Finalisieren und beim Stornieren (beide vergeben eine Rechnungsnummer) wird geprüft, ob
die Nummer schon als Rechnung aus dem alten Programm existiert (gleiche Ziffern und Buchstaben, egal welche Trennzeichen). Dann gibt
es **409** mit Hinweis auf den Nummernkreis, es wird nichts vergeben, der Entwurf bleibt Entwurf und der Zähler unverändert. Umgekehrt
lehnt der Import eine Altnummer ab, die es schon als Bilantiq-Rechnung gibt (Phase 4). Beide Richtungen sind damit abgesichert.

**Umzugsassistent** (Verwalten, Datenumzug; auch unter Mehr und als Schnellaktion der Suche)

- Checkliste mit acht Schritten: Beim alten Anbieter exportieren, Kontakte übernehmen, Produkte übernehmen (optional), Rechnungsliste
  und PDFs übernehmen, Nummernkreis fortsetzen, Offene Posten prüfen (nur Info), Kontoauszug importieren (optional, ab Pro),
  Steuerberatung informieren (optional). Jeder Schritt führt an die richtige Stelle (Kontakte-Import, Produkte-Import, Reiter für das
  alte Programm, Bank, ...).
- **Der Stand wird aus den Daten abgeleitet** (nicht zurückgenommene Importe, Altrechnungen, Nummernkreis, Bankkonto, Steuerberater),
  es gibt keinen eigenen Zustand, der veralten könnte. „Nicht nötig“ erscheint, wenn es nichts zu tun gibt (kein Altrechnungsbestand,
  keine offenen Posten). Ein zurückgenommener Import zählt nicht mehr.
- Schritte, die nur der Inhaber ausführen darf, sind für Mitglieder gesperrt und erklärt.
- **Erste Schritte** haben einen neuen optionalen Schritt „Daten vom alten Anbieter übernehmen“.
- Der Export-Schritt erinnert daran, den vollständigen Original-Export zehn Jahre aufzubewahren (GoBD).

## Annahmen, die ich getroffen habe

- **Keine Anleitungen für einzelne Programme.** Menüwege bei lexoffice, sevdesk und anderen ändern sich und lassen sich ohne
  Zugang zu den Programmen nicht prüfen. Der Assistent sagt das offen.
- **Nur das Format `RE-JJJJ-NNNN` des laufenden Jahres** fließt in den Vorschlag ein. Andere Formate („2026-0150“, „R-150“) können
  nicht mit Bilantiq-Nummern kollidieren, weil die Zeichenfolge eine andere ist, und werden nicht berücksichtigt. Ein eigenes
  Nummernformat (Präfix) gibt es nicht.
- **Jahreswechsel:** Der Zähler gilt je Jahr und beginnt im neuen Jahr bei 1. Eine Kollision im neuen Jahr (eine Altrechnung
  „RE-2027-0001“) wird erst beim Finalisieren erkannt (409), nicht vorab angezeigt. Das Jahr zählt nach UTC, wie die bisherige
  Vergabe, rund um Neujahr kann es vom lokalen Datum abweichen.
- **Das Anheben lässt eine Lücke** in der Bilantiq-Nummernfolge (die übersprungenen Nummern gehören dem alten Programm). Sie steht im
  Änderungsprotokoll. Ob eine Betriebsprüfung diese Lücke ohne Rückfrage akzeptiert, ist nicht steuerrechtlich geprüft.
- **Nur Rechnungsnummern.** Angebote, Auftragsbestätigungen und Lieferscheine (AN, AB, LS) werden nicht importiert und haben keinen
  Abgleich.
- **„Beim alten Anbieter exportiert“ ist eine Ableitung:** Der Schritt gilt als erledigt, sobald irgendein Import existiert. Ob der
  Original-Export aufbewahrt wird, weiß Bilantiq nicht.
- **Gleichzeitiger Zugriff nicht geprüft.** Auf Postgres ist der Zähler beim Vergeben gesperrt. Die Prüfung gegen Altrechnungen ist
  eine Momentaufnahme: Ein Import, der genau gleichzeitig läuft, könnte dazwischen kommen. Der Import prüft in die andere Richtung
  ebenfalls, aber die beiden Prüfungen sind nicht in einer gemeinsamen Sperre.
- **Fortschritt der Ersten Schritte:** Der neue optionale Schritt zählt wie der Steuerberater-Schritt in „x von 8“ mit. Wer keinen
  Umzug braucht, erreicht dort rechnerisch nie 100 %, die Seite meldet „Alles eingerichtet“ trotzdem, sobald die Pflichtschritte
  erledigt sind. Das war schon beim Steuerberater-Schritt so und ist hier nicht geändert.
- **Laufzeit nicht gemessen:** Der Stand liest die Rechnungsnummern aller Altrechnungen (verschlüsselt, ein Wert je Rechnung). Bei
  sehr großen Archiven kann das spürbar werden.

## Geprüft und nicht geprüft

- Backend: 14 Tests in `tests/test_umzug.py` (Nummernkreis: Start, vergebene Nummern, Altnummern in mehreren Schreibweisen,
  Setzen nur durch den Inhaber, nur nach oben, nicht unter vergebene oder alte Nummern, Mandantentrennung; Absicherung beim
  Finalisieren und Stornieren inklusive unveränderten Zählers; Umzugsstatus in allen Phasen), dazu die angepassten Tests der Ersten
  Schritte. Die komplette Suite läuft (690 Tests).
- Oberfläche: im echten Chromium gegen einen simulierten Server durchgespielt, als Inhaber und als Mitglied, auf 1280, 390 und 320 px
  ohne horizontales Überlaufen: Fortschritt, alle Schritte und ihre Ziele, Nummernkreis mit Warnung, zu niedriger Eingabe und
  Vorschlag, Einstellungen, Schnellaktion der Suche.
- **Nicht geprüft:** das echte Backend im Browser, gleichzeitige Zugriffe auf Postgres, der Jahreswechsel, Firefox und Safari,
  Screenreader.
