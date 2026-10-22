# Mitmachen bei Bilantiq

Schön, dass du helfen willst. Bilantiq ist ein Open-Source-Projekt (AGPL-3.0) zum Selbst-Hosten. Bitte lies vorher kurz
[README.md](README.md) und den [Verhaltenskodex](CODE_OF_CONDUCT.md).

## Bevor du anfängst

- **Issue zuerst** bei allem, was größer ist als ein Tippfehler oder ein kleiner Fehler: kurz beschreiben, was du vorhast. So
  vermeiden wir doppelte Arbeit und Richtungsstreit im Pull Request.
- **Sicherheitslücken nicht als Issue melden**, sondern vertraulich, siehe [SECURITY.md](SECURITY.md).
- **Keine echten Daten** in Issues, Logs, Screenshots oder Tests: keine echten Rechnungen, Belege, Kundennamen, IBANs,
  Steuernummern, Schlüssel oder Passwörter. Nimm erfundene Daten (z. B. `example.org`).

## Entwicklung einrichten

Backend und Frontend starten, Tests laufen lassen und Konventionen stehen in der [README](README.md), Abschnitt Entwicklung.
Vor einem Pull Request müssen diese vier Befehle sauber durchlaufen:

```bash
cd backend  && pytest -q
cd frontend && npx tsc -b --noEmit && npm run lint && npm run build
```

Die Postgres-RLS-Tests (Mandantentrennung) laufen nur mit `TEST_DATABASE_ADMIN_URL` (siehe `backend/scripts/rls_testlauf.sh`).
Wenn du etwas an Mandantentrennung, Verschlüsselung oder Anmeldung änderst, lass sie bitte laufen oder sag im Pull Request,
dass du es nicht konntest.

## Regeln für Änderungen

1. **Tests gehören dazu.** Neue Funktion oder behobener Fehler: ein Test, der ohne deine Änderung fehlschlägt.
2. **Schemaänderungen nur per neuer Alembic-Migration** (`backend/migrations/versions/`). Bestehende Migrationen werden nicht
   umgeschrieben. Prüfe, dass `alembic heads` genau einen Head liefert.
3. **Mandantentrennung nicht umgehen.** Neue Tabellen mit Mandantenbezug brauchen Row-Level-Security und einen Test; neue
   Routen müssen in `docs/autorisierungs-matrix.md` bzw. im zugehörigen Test eingetragen werden.
4. **Sensible Daten verschlüsselt speichern** (siehe `app/core/key_management.py`) und nicht in Logs schreiben.
5. **Ehrlich über Grenzen sein.** Nichts als „geprüft", „zertifiziert" oder „konform" beschreiben, was nicht belegt ist
   (XRechnung, ZUGFeRD, DATEV, GoBD, Steuerrecht). Annahmen und Einschränkungen gehören in die Doku und in Kommentare.
6. **Keine neuen Abhängigkeiten ohne Grund.** Begründe jede neue Bibliothek im Pull Request; Lizenz muss zur AGPL-3.0 passen.
7. **Keine Cloud-Dienste als Pflicht.** Bilantiq soll vollständig selbst betreibbar bleiben. Optionale Integrationen sind
   willkommen, wenn sie ausgeschaltet bleiben können und nichts ohne Zustimmung nach außen senden.
8. **Keine Bezahl- oder Tarifschranken** im Code. Alle Funktionen stehen allen Betreibern offen.

## Pull Requests

- Kleine, thematisch getrennte Pull Requests sind leichter zu prüfen als ein großer.
- Beschreibe das *Warum* und, wenn nötig, wie du es geprüft hast.
- Commit-Nachrichten gern auf Deutsch oder Englisch, prägnant, mit dem Grund der Änderung.
- Mit deinem Beitrag stimmst du zu, dass er unter der [AGPL-3.0](LICENSE) des Projekts veröffentlicht wird.

## Name und Logo

Der Code steht unter der AGPL-3.0. Name „Bilantiq" und Logo sind davon ausgenommen, siehe [TRADEMARK.md](TRADEMARK.md).
