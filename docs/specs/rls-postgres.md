# Spec: Mandantenkontext und Datenbank-RLS ohne BYPASSRLS

Status: GEBAUT im Code, Betriebsschritt (BYPASSRLS entziehen) auf dem Server offen.

## Problem

1. `set_rls_mandant` benutzte `SET LOCAL … = :parameter`. Postgres kennt in `SET` keine Bind-Parameter, `psycopg` meldet
   SQLSTATE 42601. Jede angemeldete Anfrage konnte scheitern.
2. Der Mandant galt nur bis zum Ende der Transaktion. Die Anwendung committet mehrfach je Anfrage, danach fehlte er.
3. Registrierung, Anmeldung und MFA-Schritt (früher auch der Webhook der Bezahlfunktion) arbeiten, bevor ein Mandant feststeht. Ohne `BYPASSRLS`
   sehen sie RLS-Tabellen nicht oder dürfen nicht hineinschreiben.

## Lösung

- `set_config('app.current_mandant_id', :id, true)` statt `SET LOCAL`.
- Die Session merkt sich den Mandanten (`session.info`), ein `after_begin`-Ereignis setzt ihn bei jeder neuen Transaktion neu.
- Migration `0035`: drei enge `SECURITY DEFINER`-Funktionen liefern nur eine Mandanten-ID zu einem nicht erratbaren Schlüssel
  (Einladungscode, Nutzer-ID, früher Kunde der Bezahlfunktion; die dritte Funktion entfernt Migration `0039`). Aufruf über `app/core/rls_lookup.py`, danach `set_rls_mandant`.
- Registrierung legt die Mandanten-ID vor dem Einfügen fest und setzt den Kontext zuerst. Der MFA-Schritt setzt den
  Kontext aus dem signierten Token. Anmeldung findet den Mandanten über die Funktion.
- `scripts/runtime_rolle.sql` legt die Laufzeitrolle (ohne Superuser, ohne `BYPASSRLS`, Audit-Log nur Lesen und Einfügen) an
  und vergibt `EXECUTE` auf die Funktionen. Nach jeder Migration erneut ausführen.

## Prüfung

- Postgres-Testmodus: `TEST_DATABASE_ADMIN_URL` (Administrator, für Schema und Testdaten) und `DATABASE_URL` (Laufzeitrolle).
  Das Schema kommt aus den Migrationen, also mit allen RLS-Regeln. Die ganze Suite (400 Tests) läuft so grün; im
  normalen SQLite-Lauf sind es 393 grün und 7 übersprungene RLS-Tests.
  Zum Selbsttesten: `cd backend && scripts/rls_testlauf.sh` (startet eine temporäre Postgres-Instanz, braucht `initdb`, `pg_ctl`, `psql`).
- `tests/test_rls_postgres.py`: Rolle ohne BYPASSRLS, ohne Kontext keine Zeilen, Kontext trennt Mandanten, Kontext überlebt
  Commit, Schreiben in fremden Mandanten wird abgewiesen, Lookup-Funktionen, Audit-Log append-only. Gegenprobe: Ohne das
  `after_begin`-Ereignis schlägt der Commit-Test fehl.

## Grenzen (ehrlich)

- **Auf dem Server ist noch nichts geändert.** Erst nach Einspielen, Migration 0035, `runtime_rolle.sql` und Entzug von
  `BYPASSRLS` greift die Datenbanktrennung wirklich.
- Getestet mit Postgres 18 lokal; auf dem Server läuft eine andere Version.
- Tabellen **ohne** RLS-Regel: `users`, `webhook_ereignisse`, `auftragsbestaetigung_positionen`, `lieferschein_positionen`
  und die Nummernkreise für Auftragsbestätigung und Lieferschein. Sie sind nur durch die Filter der Anwendung geschützt.
- Die expliziten Filter der Anwendung wurden nicht vollständig auditiert. Die Testsuite deckt nur die vorhandenen Abläufe ab.
- Nebenläufigkeit (gleichzeitige Anfragen derselben Session-Pools) wurde nicht gesondert getestet. Der Kontext hängt an der
  Session, nicht an der Verbindung, und wird bei jeder Transaktion neu gesetzt.
- Die Funktionen sind für `PUBLIC` gesperrt und nur der Laufzeitrolle freigegeben. Wer die Rolle nutzen kann, kann mit
  bekanntem Einladungscode oder Nutzer-ID die Mandanten-ID erfragen. Beides ist nicht erratbar, aber auch kein Geheimnis
  im Sinne eines Passworts.
- Migration `0035` hat `down_revision = 0026`. Beim Zusammenführen mit `feature/datenumzug` (Head `0034`) auf `0034` setzen.
  Die dortigen neuen Tabellen haben eigene RLS-Regeln; sie sind in diesem Lauf nicht getestet.
