# Lasttest

Stand: 14. Oktober 2026.. Skript: `backend/scripts/lasttest.py`.

## Was das Skript tut

Nur `asyncio` und `httpx` (beides ohnehin Backend-Abhängigkeiten). Pro virtuellem Nutzer:

1. **Setup** (getrennt ausgewertet): Registrierung eines eigenen Mandanten, ein Kontakt, ein Rechnungsentwurf.
2. **Lastphase** in einer Schleife ohne Denkpausen, gewichtete Mischung (Standard `login:1,listen:3,dashboard:2,pdf:2`):
   - `login`: `POST /auth/login`
   - `listen`: `GET /invoices` und `GET /kontakte`
   - `dashboard`: `GET /berichte/dashboard`
   - `pdf`: `GET /invoices/{id}/pdf` (Rechnungs-PDF, prüft zusätzlich den `%PDF`-Header)
3. Ausgabe pro Endpunkt: Anzahl, Fehler, p50/p95/p99/max in ms, Statuscodes; Gesamtfehlerquote und Durchsatz. `--json-out` speichert das Ergebnis. Exit 1, wenn die Fehlerquote über `--max-fehlerquote` (Standard 1 %) liegt.

```
cd backend
python scripts/lasttest.py --base-url http://127.0.0.1:8010 --nutzer 25 --dauer 30
python scripts/lasttest.py --help
```

## Schutz gegen Fehlbedienung

- Ohne Zusatzoption sind nur `localhost`, `127.0.0.1`, `::1` als Ziel erlaubt.
- Für eine eigene Testinstanz: `--base-url https://api-test.<domain> --erlaube-fremden-host`. Nie gegen eine Instanz mit echten Daten laufen lassen.
- Der Test legt Konten `lasttest-<lauf>-<n>@example.com` und Wegwerfdaten an. Nur gegen Wegwerf-Datenbanken verwenden.
- Registrierungen sind nicht ratenbegrenzt (im Code keine Registrierungs-Ratenbegrenzung gefunden). Der Test würde auf einer öffentlich erreichbaren Staging-Instanz also beliebig viele Konten erzeugen.

## Probelauf (14.10.2026) und gemessene Werte

**Aufbau (alles lokal auf einem Entwicklungsrechner):**
- Backend: eine uvicorn-Instanz (ein Prozess, ein Worker, wie im `backend/Dockerfile`) auf Port 8010, Wegwerf-SQLite-Datei, Wegwerf-`.env` mit Zufallswerten im Scratchpad, Dummy-SMTP-Werte, nie angesprochen.
- Client: dasselbe Skript auf derselben Maschine (AMD Ryzen 5 7520U, 8 logische Kerne).
- **Die Maschine war währenddessen nicht frei:** Load Average 9,9 bei 8 Kernen (andere Entwicklungsprozesse liefen parallel). Die absoluten Zeiten sind deshalb eher pessimistisch und nicht reproduzierbar genau.
- 30 s Lastphase je Lauf, ein Lauf pro Nutzerzahl, jeweils 0 Fehler (alle Antworten 2xx).

Latenzen in Millisekunden (Lastphase, ohne Setup):

**10 Nutzer** (30,1 s, 2302 Anfragen, 76,5 Anfragen/s)

| Endpunkt | n | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| dashboard | 413 | 154,8 | 244,6 | 283,4 | 307,9 |
| liste_kontakte | 634 | 85,3 | 147,9 | 174,3 | 238,2 |
| liste_rechnungen | 634 | 108,1 | 169,1 | 195,7 | 225,2 |
| login | 213 | 236,8 | 542,2 | 689,5 | 726,3 |
| rechnungs_pdf | 408 | 124,9 | 194,2 | 230,1 | 273,9 |

**25 Nutzer** (30,2 s, 2376 Anfragen, 78,7 Anfragen/s)

| Endpunkt | n | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| dashboard | 417 | 320,9 | 615,6 | 764,1 | 1085,3 |
| liste_kontakte | 663 | 193,2 | 443,3 | 555,1 | 745,4 |
| liste_rechnungen | 663 | 262,9 | 542,9 | 710,0 | 1002,3 |
| login | 226 | 507,7 | 1221,2 | 1559,6 | 1614,0 |
| rechnungs_pdf | 407 | 341,4 | 621,1 | 725,2 | 1035,4 |

**50 Nutzer** (30,7 s, 2344 Anfragen, 76,3 Anfragen/s)

| Endpunkt | n | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| dashboard | 399 | 564,2 | 1310,3 | 1851,3 | 2365,5 |
| liste_kontakte | 660 | 476,7 | 1094,1 | 1480,5 | 1812,8 |
| liste_rechnungen | 660 | 561,7 | 1368,6 | 1898,7 | 3142,8 |
| login | 237 | 856,3 | 2393,1 | 2785,4 | 3163,6 |
| rechnungs_pdf | 388 | 650,3 | 1516,2 | 1997,7 | 2592,3 |

Setup (Registrierung inkl. Passwort-Hashing): p50 etwa 170 bis 250 ms je Registrierung bei bis zu 5 parallelen Registrierungen.

## Was daraus folgt (und was nicht)

- Der Durchsatz bleibt bei 10, 25 und 50 Nutzern bei etwa 76 bis 79 Anfragen/s. Mehr Nutzer verlängern nur die Antwortzeiten: **der Engpass liegt in diesem Aufbau beim einen Backend-Prozess bzw. bei der gemeinsam genutzten CPU**, nicht bei der Datenbank (SQLite, im Test ohne Schreib-Konkurrenz außer Login-/Audit-Schreibzugriffen). Das ist eine Beobachtung aus dem Durchsatzverhalten, keine Profilerstellung.
- `login` ist erwartungsgemäß am langsamsten (Passwort-Hash, mehr Schreibzugriffe für Audit-Log/Sitzung).
- Die Last ist härter als echte Nutzer: Der Test arbeitet ohne Denkzeit. 50 Testnutzer entsprechen in Anfragen pro Sekunde deutlich mehr als 50 echte Personen im Browser. Eine verlässliche Umrechnung auf "so viele echte Nutzer trägt das System" gibt es hier **nicht**.
- Im Test lief kein Reverse-Proxy (Caddy), kein TLS, kein Docker und keine Netzwerklatenz.

## Grenzen (ehrlich)

- **SQLite ist nicht die Produktion.** Produktion läuft auf PostgreSQL mit Row-Level-Security (pro Anfrage `set_config`, zusätzliche Policy-Prüfung) und einer Laufzeitrolle ohne BYPASSRLS. Das kostet Zeit und kann Latenzen und Durchsatz deutlich verändern, in beide Richtungen (echte Parallelität bei Schreibzugriffen versus RLS-Overhead). Diese Zahlen dürfen nicht auf Produktion übertragen werden.
- Nicht gemessen: OCR-Dauer, Belegupload, Mahnwesen, XRechnung/ZUGFeRD-Erzeugung, E-Mail-Versand, parallele Schreiblast auf denselben Mandanten, Langzeit-/Soak-Test, Speicherverbrauch.
- Eine Lastquelle, ein Prozess: Der Python-Client kann bei hohen Zahlen selbst Engpass werden.
- Keine Ziel-Schwellen festgelegt (z. B. "p95 unter 1 s bei N Nutzern"). Die müssen Sie als Betreiber nach dem Lauf auf Staging festlegen.

## Empfohlener nächster Schritt (Betreiber)

1. Auf **Staging** (PostgreSQL, Laufzeitrolle, Caddy, TLS) denselben Lauf wiederholen:
   `python scripts/lasttest.py --base-url https://api-staging.<domain> --erlaube-fremden-host --nutzer 25 --dauer 60 --json-out staging-25.json`
   danach 10 und 50. Die Werte dieser Datei nur als Vergleichsgrundlage nehmen.
2. Währenddessen auf dem Staging-Server `docker stats` und `docker compose logs backend` beobachten (CPU, Speicher, Fehler).
3. Erst mit den Staging-Zahlen entscheiden, ob mehrere uvicorn-Worker nötig sind (der Dockerfile startet einen).
