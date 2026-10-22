# Spec: Oberfläche überarbeitet (Seitenleiste, Erste Schritte, KI-Chat)

Status: GEBAUT (Branch `feature/ui-feinschliff`, aufbauend auf `integration/2026-10-09`).
Anlass: Rückmeldung nach dem ersten Durchklicken der Desktop-Ansicht.

## Probleme und Lösungen

- **Logo und Slogan in der Kopfzeile verschoben:** Die Kopfzeile war über die volle Breite
  zentriert, der Inhalt aber im Bereich rechts der Seitenleiste. Beide Spalten saßen 120 px
  versetzt. Am Desktop (ab 1024 px) wandert das Logo jetzt oben in die Seitenleiste (weiß, per
  Filter aus dem Primärlogo), der Slogan unten dazu, die Kopfzeile entfällt. Auf dem Handy und auf
  den Anmeldeseiten bleibt sie wie bisher.
- **Seitenleiste scrollte:** Zeilenhöhe 44 auf 40 px, Unterpunkte 34 px, Abstände enger. Die
  Leiste ist jetzt volle Höhe mit festem Kopf und Fuß, nur der Mittelteil scrollt (bei sehr
  kleinen Fenstern) und zeigt dann eine schmale, dezente Leiste.
- **"Erste Schritte" fehlte:** Die Seite gibt es jetzt. `GET /erste-schritte` leitet den
  Fortschritt aus vorhandenen Daten ab (Unternehmensdaten, Rechnungsdesign, Kunde, finale
  Rechnung, Beleg, Bankkonto, Steuerberatung als optional). Es gibt keinen eigenen Zustand, der
  veralten kann. Die Seite zeigt Fortschrittsbalken, den nächsten Schritt hervorgehoben und
  springt per Klick zur passenden Seite. Auch unter Mehr erreichbar.
- **KI-Assistent als Chat:** Begrüßung "Wie kann ich dir helfen?", großes Eingabefeld (wächst mit,
  Enter sendet, Shift+Enter neue Zeile), Vorschlags-Chips, Verlauf mit Nutzer-Sprechblase rechts
  und Antwort links mit Avatar, Tipp-Anzeige, Fehlermeldungen im Verlauf, "Neuer Chat", Eingabe
  unten angeheftet, Hinweis zur Verlässlichkeit. Die Funktionen des Assistenten selbst
  (`/ai/assistent`, nur lesend, nur Business) sind unverändert.
- **Tabellen:** Die Zeilenlinie riss in der Aktionen-Spalte ab (`td` war als Flex-Box gesetzt).
  Die Belegliste zeigt Betrag und Datum formatiert (`1.213,80 €`, `08.10.2026`) statt roh.

## Annahmen

- Die neue Oberfläche wurde im Browser mit simulierten Serverantworten geprüft (Desktop und
  390 px breit), nicht mit echter Anmeldung.
- Der Chat hält den Verlauf nur im Browser, ohne Speicherung und ohne Streaming der Antwort.
  Der Assistent antwortet weiter als Ganzes.
- Das weiße Logo entsteht per CSS-Filter aus dem Primärlogo, beide Farben werden dabei weiß.
  Eine eigene Negativ-Variante aus dem Brand-Paket wäre sauberer.
