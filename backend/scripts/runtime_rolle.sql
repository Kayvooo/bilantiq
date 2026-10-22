-- Datenbankrolle für die laufende Anwendung (ohne Superuser, ohne BYPASSRLS, ohne Schemaänderungen).
-- Aufruf als Administrator:  psql -v rolle=bilantiq_runtime -v passwort="'…'" -f runtime_rolle.sql <datenbank>
-- Nach jeder Migration erneut ausführen, damit neue Tabellen die Rechte bekommen.
\if :{?rolle} \else \set rolle bilantiq_runtime \endif

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'rolle', :'passwort')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'rolle') \gexec
SELECT format('ALTER ROLE %I NOBYPASSRLS', :'rolle') \gexec

SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'rolle') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'rolle') \gexec
SELECT format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', :'rolle') \gexec
-- Das Audit-Log ist append-only.
SELECT format('REVOKE UPDATE, DELETE, TRUNCATE ON audit_log_eintraege FROM %I', :'rolle') \gexec
-- Die Versionstabelle der Migrationen gehört dem Administrator.
SELECT format('REVOKE ALL ON alembic_version FROM %I', :'rolle') \gexec
-- Lookup-Funktionen für Vorgänge ohne Mandantenkontext (Migration 0035).
SELECT format('GRANT EXECUTE ON FUNCTION bq_mandant_aus_einladung(text), bq_mandant_des_nutzers(text) TO %I', :'rolle') \gexec
