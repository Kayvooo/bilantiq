# Bilantiq: Kontext für KI-Assistenten und neue Mitwirkende

Bilantiq ist eine Open-Source-Buchhaltungssoftware (AGPL-3.0) zum Selbst-Hosten, mit Fokus auf DSGVO und GoBD. Es gibt keinen
gehosteten Dienst, keine Tarife und keine Bezahlfunktion. Überblick, Schnellstart und Grenzen: `README.md`. Regeln fürs
Mitmachen: `CONTRIBUTING.md`. Betrieb: `docs/self-hosting.md`.

## Arbeitsweise

1. Bei neuen Features zuerst die passende Spec in `docs/specs/` lesen oder eine anlegen (mit einem ehrlichen Abschnitt
   „Annahmen, die ich getroffen habe"). Dann Backend (Models, Schemas, Routen, Migration), Tests, volle Suite
   (`cd backend && pytest -q`), bei Frontend-Änderungen `npx tsc -b --noEmit`, `npm run lint`, `npm run build`.
2. **Ehrlichkeit über Grenzen ist Teil des Stils.** Nichts als geprüft oder konform darstellen, was nicht belegt ist:
   XRechnung wird gegen die KoSIT-Konfiguration mit Saxon geprüft, aber nicht mit dem Original-Validator und nicht zertifiziert;
   ZUGFeRD ist best-effort; der DATEV-Export ist nicht gegen echtes DATEV getestet; SKR03-Kontonummern sind nicht
   steuerberatergeprüft; Mahngebühren sind Platzhalter; die Cashflow-Prognose ist bewusst deterministisch; die
   Lohnvorbereitung berechnet keine Lohnsteuer oder Sozialversicherung. Solche Einschränkungen offen in Specs und Kommentaren
   benennen.
3. Eine Bankanbindung (finAPI o. ä.) ist bewusst ausgeklammert; es gibt nur den Kontoauszug-Import (`app/bank/`).
4. Keine echten Daten, Schlüssel oder personenbezogenen Angaben in Code, Tests, Doku oder Commits.
5. Commit-Nachrichten kurz, mit dem Grund der Änderung (Deutsch oder Englisch).

## Technischer Überblick

- Backend: Python (3.13/3.14), FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest (`backend/`). Migrationen in
  `backend/migrations/versions/` (linear, aktueller Head: `alembic heads`; bestehende Migrationen nie umschreiben).
- Mandantentrennung: Postgres Row-Level-Security (`app/core/rls.py`, `docs/specs/rls-postgres.md`) plus Anwendungs-Ebene als
  Ersatz für SQLite. Neue Tabellen mit Mandantenbezug brauchen RLS und einen Test. Die Postgres-Tests laufen nur mit
  `TEST_DATABASE_ADMIN_URL` (`backend/scripts/rls_testlauf.sh`).
- Sicherheit: Argon2id, serverseitig widerrufbare Sitzungen (`security_version`), optionale MFA (TOTP mit Wiederherstellungs-
  codes), AES-256-GCM-Envelope-Verschlüsselung sensibler Felder und Dateien mit versioniertem Schlüsselbund
  (`app/core/key_management.py`), Schlüsselrotation per `backend/scripts/rotate_encryption.py`, append-only Audit-Log.
  Autorisierungsübersicht: `docs/autorisierungs-matrix.md`.
- Registrierung: `REGISTRATION_MODE` = `first_account` (Standard), `closed` oder `open` (`app/auth/routes.py`).
- Dateispeicher: alles unter `STORAGE_DIR` (`app/core/storage_check.py` prüft beim Start). E-Mail (SMTP) ist optional.
- XRechnung: Erzeugung in `app/invoices/e_invoice.py`, Prüfung in `app/invoices/e_invoice_validation.py`
  (`XRECHNUNG_PRUEFUNG`: `aus`, `warnen` als Standard, `blockieren`). Die Prüfregeln liegen nicht im Repository, sondern werden
  mit `backend/scripts/kosit_regeln_holen.py` geholt (`docs/xrechnung-validierung.md`). Empfang: `app/receipts/e_rechnung.py`.
- Belegerfassung: lokal mit Tesseract, regelbasiert, keine Cloud-API.
- Lokale KI (`app/ai/`): OpenAI-kompatible Schicht zu einem selbst betriebenen Dienst, `AI_ENABLED=false` als Standard, kein
  Cloud-Fallback, das Modell bekommt keinen Datenbankzugriff. Phase E ist nur lesend, F erzeugt nur Formularentwürfe, G nur
  Textvorschläge (`docs/specs/phase-e-f-g-lokale-ki.md`).
- Frontend: React 19, TypeScript, Vite, handgeschriebenes CSS mit Tokens in `frontend/src/styles/`, keine UI-Bibliothek, keine
  Drittanbieter-Webfonts. Der PDF-Rechnungs-Designer liest Vorlage, Farbe und Logo vom Mandanten (`app/core/document_pdf.py`).
- Tests: Die Dev-Datenbank (SQLite) entsteht per `create_all()` und ändert bestehende Spalten nicht; bei Schemaänderungen
  die Datei löschen.

## Name und Logo

Code unter AGPL-3.0, Name und Logo sind davon ausgenommen (`TRADEMARK.md`). Forks bitte mit eigenem Namen.
