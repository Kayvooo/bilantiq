# Autorisierungs-Matrix

Stand: 14. Oktober 2026. Grundlage: alle 170 Routen der laufenden FastAPI-App
(165 beim Sweep, danach vier Routen für Passwort-Reset/MFA-Wiederherstellung und `/health/ready`; Methode + Pfad), erzeugt per Introspektion der Abhängigkeiten und des Handler-Codes, danach von Hand gegengelesen.
Seitdem entfallen sind die sechs Routen der Bezahlfunktion (`/billing/*`, `/zahlen/{token}`, `/invoices/{id}/zahllink`); die Routenzahlen oben
sind der Stand vor der Entfernung.
Die Festlegungen sind durch Tests abgesichert (`backend/tests/test_autorisierung.py`, `backend/tests/test_mandantentrennung.py`);
eine neue Route, die hier nicht passt, lässt die Tests rot werden und zwingt zu einer bewussten Entscheidung.

## Spalten

**MFA-Pflicht (seit F3):** Bei `angemeldet` und `Owner` prüft `require_full_auth` zusätzlich, ob die aktuelle Mandantenrolle
laut `MFA_PFLICHT` MFA braucht und ob das Konto sie eingerichtet hat; sonst 401. Siehe `docs/specs/mfa-pflicht.md`.

- **Auth:** `angemeldet` = `require_full_auth` (JWT, Scope `full`, Sitzung nicht widerrufen, `security_version` aktuell,
  Mitgliedschaft im Mandanten des Tokens); `Owner` = zusätzlich Mandantenrolle `owner` (Rolle wird je Aufruf aus der Datenbank
  gelesen, nicht aus dem JWT); `Pre-MFA-Token` = nur der Zwischenschritt nach der Passwortprüfung; `öffentlich` = keine Anmeldung.
- **Tarife:** Es gibt keine Tarife, Limits oder Funktionssperren mehr (Stand Oktober 2026); alle Funktionen stehen jedem
  angemeldeten Nutzer offen. Die frühere Spalte „Tarif-Gate“ und die HTTP-402-Antworten sind entfallen.
- **Mandantenbindung:** Der Mandant stammt immer aus dem signierten Token, nie aus der Anfrage. Objekte werden über
  `get_scoped_or_404` bzw. mit Filter auf `mandant_id` geladen; unter Postgres erzwingt zusätzlich RLS die Trennung.
  Nachgewiesen für alle 61 Routen mit Pfadparametern (Mandant A ruft mit den IDs von B auf: immer 404) in `test_mandantentrennung.py`.

## Befunde dieses Sweeps

Behoben (mit Tests):

1. **Lohn-Routen waren für jedes Mitglied lesbar und schreibbar** (Gehälter und Namen aller Beschäftigten). Jetzt komplett
   Owner-only (`/lohn/*`, Router-Abhängigkeit).
2. **Firmen- und Bankdaten (`PATCH /auth/mandant`) konnte jedes Mitglied ändern**, auch die IBAN, die auf jeder Rechnung steht
   (Zahlungsumleitung bei einem übernommenen Mitgliedskonto). Jetzt: Änderungen an Stamm-/Bankdaten nur Owner; unveränderte Werte
   (das Design-Formular schickt IBAN/BIC mit) und reine Design-Felder bleiben für Mitglieder möglich.
3. **Fünf Tabellen ohne RLS** (Nummernkreise für Auftragsbestätigung/Lieferschein, Steueranteile, deren Positionstabellen):
   Migration 0037, plus Test, der jede künftige Tabelle ohne Policy findet.
4. Kein serverseitiges Abmelden: `POST /auth/logout` ergänzt.

Offen / Entscheidung des Betreibers (nicht ungefragt geändert):

1. **Rollenmodell ist grob** (`owner` / `mitglied`): Mitglieder dürfen sonst alles Fachliche, u. a. Buchhaltungseinstellungen ändern
   (`PUT /buchhaltungseinstellungen`), Bankkonten anlegen und Kontoauszüge importieren, DATEV-Export ziehen, Rechnungen stornieren,
   Belege löschen, das eigene Konto anonymisieren. Für eine Beta mit vertrauten Mitarbeitenden vertretbar; vor öffentlichem Start
   entscheiden, ob es eine Rolle "nur Erfassen" braucht.
2. **`DELETE /auth/me`** (Konto anonymisieren) verlangt jetzt Passwort und, bei aktivem MFA, den aktuellen Code im Body; Fehlversuche zählen im gemeinsamen Brute-Force-Zähler (Sperre nach 5). Offen bleibt: Ist der Nutzer der einzige Owner, bleibt der Mandant ohne Owner zurück (Produktentscheidung, nicht geändert). **Frontend muss nachziehen** (`deleteAccount` in `frontend/src/features/auth/api.ts`, Aufruf in `SecurityPrivacyPage.tsx`).
3. **Alle Mitglieder sehen die E-Mail-Adressen aller Kollegen** (`GET /auth/mitglieder`) und die Einladungscodes nur der Owner.

## Matrix

Reihenfolge nach Pfad. Gleiche Zeilen mit unterschiedlichen Methoden sind getrennt aufgeführt.

| Methode | Pfad | Auth | Mandantenbindung | Bemerkung |
| --- | --- | --- | --- | --- |
| `POST` | `/ai/angebotsentwurf` | angemeldet | ja |  |
| `POST` | `/ai/assistent` | angemeldet | ja |  |
| `POST` | `/ai/rechnungsentwurf` | angemeldet | ja |  |
| `POST` | `/ai/textvorschlag` | angemeldet | ja |  |
| `GET` | `/altrechnungen` | angemeldet | ja |  |
| `POST` | `/altrechnungen/pdfs` | angemeldet | ja |  |
| `GET` | `/altrechnungen/{altrechnung_id}/pdf` | angemeldet | ja |  |
| `POST` | `/altrechnungen/{altrechnung_id}/pdf` | angemeldet | ja |  |
| `POST` | `/altrechnungen/{altrechnung_id}/zahlung` | angemeldet | ja |  |
| `GET` | `/angebote` | angemeldet | ja |  |
| `POST` | `/angebote` | angemeldet | ja |  |
| `GET` | `/angebote/{quote_id}` | angemeldet | ja |  |
| `POST` | `/angebote/{quote_id}/ablehnen` | angemeldet | ja |  |
| `POST` | `/angebote/{quote_id}/annehmen` | angemeldet | ja |  |
| `POST` | `/angebote/{quote_id}/in-rechnung-umwandeln` | angemeldet | ja |  |
| `GET` | `/angebote/{quote_id}/pdf` | angemeldet | ja |  |
| `POST` | `/angebote/{quote_id}/per-email-senden` | angemeldet | ja | Versandlimit je Mandant (30/h, 100/Tag), Reply-To |
| `POST` | `/angebote/{quote_id}/versenden` | angemeldet | ja |  |
| `GET` | `/anlagen` | angemeldet | ja |  |
| `POST` | `/anlagen` | angemeldet | ja |  |
| `GET` | `/auftragsbestaetigungen` | angemeldet | ja |  |
| `POST` | `/auftragsbestaetigungen` | angemeldet | ja |  |
| `GET` | `/auftragsbestaetigungen/{ab_id}` | angemeldet | ja |  |
| `GET` | `/auftragsbestaetigungen/{ab_id}/pdf` | angemeldet | ja |  |
| `GET` | `/ausgaben` | angemeldet | ja |  |
| `GET` | `/auth/briefpapier` | angemeldet | ja |  |
| `POST` | `/auth/briefpapier` | angemeldet | ja | Magic-Bytes + Pixelgrenze (Upload-Härtung) |
| `DELETE` | `/auth/briefpapier/{briefpapier_id}` | angemeldet | ja |  |
| `GET` | `/auth/datenexport` | **Owner** | ja | enthält alle Mandantendaten; **frische MFA-Bestätigung** (`gesamtexport`, HTTP 428 ohne) |
| `GET` | `/auth/einladungen` | **Owner** | ja |  |
| `POST` | `/auth/einladungen` | **Owner** | ja | **frische MFA-Bestätigung** (`benutzer_verwalten`) |
| `POST` | `/auth/einladungen/{einladung_id}/widerrufen` | **Owner** | ja |  |
| `POST` | `/auth/login` | **öffentlich** | ja | IP-Limit 30/5 min; Konto-Sperre 5 Fehlversuche/15 min; generische Fehlermeldung, Dummy-Hash gegen Zeit-Enumeration |
| `POST` | `/auth/login/mfa` | Pre-MFA-Token | ja | Pre-MFA-Token; gemeinsamer Fehlversuchszähler; IP-Limit; TOTP-Code nur einmal pro Zeitschritt (Replay-Schutz) |
| `POST` | `/auth/login/mfa/wiederherstellungscode` | Pre-MFA-Token | ja | Pre-MFA-Token; Einmalcode statt TOTP, wird verbraucht; Fehlversuche im gemeinsamen Zähler; IP-Limit; Audit `mfa_wiederherstellungscode_verwendet` |
| `POST` | `/auth/bestaetigung` | angemeldet | ja | stellt das Bestätigungs-Token aus (TOTP oder Wiederherstellungscode, 5 Minuten, an Sitzung und Aktionsklasse gebunden); IP-Limit, Fehlversuchszähler, Audit `bestaetigung_erteilt` ohne Code |
| `POST` | `/auth/logout` | angemeldet | ja | beendet nur die aktuelle Sitzung |
| `GET` | `/auth/mandant` | angemeldet | ja |  |
| `PATCH` | `/auth/mandant` | angemeldet | ja | Firmen-/Bankdaten nur Owner; Design-Felder alle Mitglieder; **IBAN/BIC-Änderung mit frischer MFA-Bestätigung** (`iban_aendern`) |
| `DELETE` | `/auth/mandant/logo` | angemeldet | ja |  |
| `GET` | `/auth/mandant/logo` | angemeldet | ja |  |
| `POST` | `/auth/mandant/logo` | angemeldet | ja | Magic-Bytes + Pixelgrenze (Upload-Härtung) |
| `POST` | `/auth/mandant/rechnungsvorlage/vorschau` | angemeldet | ja | JSON-Body statt Query (IBAN/BIC/Fußzeile nicht im Zugriffslog); GET entfernt |
| `DELETE` | `/auth/me` | angemeldet | ja | Anonymisierung des eigenen Kontos, jedes Mitglied; Body mit Passwort (+ MFA-Code bei aktivem MFA), Fehlversuche im gemeinsamen Zähler |
| `GET` | `/auth/me` | angemeldet | ja |  |
| `POST` | `/auth/mfa/setup` | Pre-MFA-Token | ja | Pre-MFA-Token |
| `POST` | `/auth/mfa/verify` | Pre-MFA-Token | ja | Pre-MFA-Token; Fehlversuchszähler; IP-Limit; Replay-Schutz; liefert bei der ersten Aktivierung einmalig 10 Wiederherstellungscodes |
| `GET` | `/auth/mitglieder` | angemeldet | ja | alle Mitglieder sehen die E-Mail-Adressen der Kollegen |
| `POST` | `/auth/mitglieder` | **Owner** | ja | **frische MFA-Bestätigung** (`benutzer_verwalten`) |
| `POST` | `/auth/mitglieder/{user_id}/entfernen` | **Owner** | ja | **frische MFA-Bestätigung** (`benutzer_verwalten`) |
| `POST` | `/auth/passwort/aendern` | angemeldet | ja | Fehlversuchszähler; beendet alle Sitzungen |
| `POST` | `/auth/passwort/vergessen` | **öffentlich** | n/a | antwortet immer gleich (202), keine Konto-Enumeration; IP-Limit 10/h, Konto-Limit 3/h; Antwortzeit aufgefüllt, Mail nach der Antwort |
| `POST` | `/auth/passwort/zuruecksetzen` | **öffentlich** | ja | Einmal-Token (256 Bit, HMAC gespeichert, 60 min) statt Anmeldung; IP-Limit 20/15 min; beendet alle Sitzungen, MFA bleibt aktiv |
| `POST` | `/auth/register` | **öffentlich** | ja | IP-Limit 10/h; Einladungscode bindet an fremden Mandanten, Nutzerlimit wird geprüft |
| `GET` | `/bank/konten` | angemeldet | ja |  |
| `POST` | `/bank/konten` | angemeldet | ja |  |
| `POST` | `/bank/konten/{konto_id}/import` | angemeldet | ja |  |
| `POST` | `/bank/konten/{konto_id}/import/vorschau` | angemeldet | ja |  |
| `GET` | `/bank/umsaetze` | angemeldet | ja |  |
| `POST` | `/bank/umsaetze/{umsatz_id}/ignorieren` | angemeldet | ja |  |
| `POST` | `/bank/umsaetze/{umsatz_id}/zuordnen` | angemeldet | ja |  |
| `POST` | `/bank/umsaetze/{umsatz_id}/zuordnung-aufheben` | angemeldet | ja |  |
| `POST` | `/bank/zuordnungen/bestaetigen` | angemeldet | ja |  |
| `GET` | `/bank/zusammenfassung` | angemeldet | ja |  |
| `GET` | `/belege` | angemeldet | ja |  |
| `POST` | `/belege` | angemeldet | ja |  |
| `GET` | `/belege/vorschlag` | angemeldet | ja |  |
| `DELETE` | `/belege/{beleg_id}` | angemeldet | ja |  |
| `GET` | `/belege/{beleg_id}` | angemeldet | ja |  |
| `POST` | `/belege/{beleg_id}/bestaetigen` | angemeldet | ja |  |
| `GET` | `/belege/{beleg_id}/datei` | angemeldet | ja |  |
| `GET` | `/berichte/bwa` | angemeldet | ja |  |
| `GET` | `/berichte/cashflow` | angemeldet | ja |  |
| `GET` | `/berichte/dashboard` | angemeldet | ja |  |
| `GET` | `/berichte/datev-export` | angemeldet | ja |  |
| `GET` | `/berichte/euer` | angemeldet | ja |  |
| `GET` | `/berichte/susa` | angemeldet | ja |  |
| `GET` | `/berichte/ustva` | angemeldet | ja |  |
| `GET` | `/buchhaltungseinstellungen` | angemeldet | ja |  |
| `PUT` | `/buchhaltungseinstellungen` | angemeldet | ja |  |
| `GET` | `/einnahmen` | angemeldet | ja |  |
| `POST` | `/einnahmen` | angemeldet | ja |  |
| `PATCH` | `/einnahmen/{einnahme_id}` | angemeldet | ja |  |
| `GET` | `/einstellungen/nummernkreis` | angemeldet | ja |  |
| `PUT` | `/einstellungen/nummernkreis` | **Owner** | ja |  |
| `GET` | `/erste-schritte` | angemeldet | ja |  |
| `GET` | `/health` | **öffentlich** | n/a | ohne Daten |
| `GET` | `/health/ready` | **öffentlich** | n/a | nur DB-Check, bei Ausfall 503 ohne Details |
| `GET` | `/invoices` | angemeldet | ja |  |
| `POST` | `/invoices` | angemeldet | ja |  |
| `POST` | `/invoices/vorschau` | angemeldet | ja |  |
| `GET` | `/invoices/{invoice_id}` | angemeldet | ja |  |
| `POST` | `/invoices/{invoice_id}/bezahlt` | angemeldet | ja |  |
| `POST` | `/invoices/{invoice_id}/e-rechnung` | angemeldet | ja |  |
| `GET` | `/invoices/{invoice_id}/e-rechnung-pruefung` | angemeldet | ja |  |
| `POST` | `/invoices/{invoice_id}/finalize` | angemeldet | ja |  |
| `POST` | `/invoices/{invoice_id}/mahnung` | angemeldet | ja |  |
| `GET` | `/invoices/{invoice_id}/mahnungen` | angemeldet | ja |  |
| `GET` | `/invoices/{invoice_id}/pdf` | angemeldet | ja |  |
| `POST` | `/invoices/{invoice_id}/storno` | angemeldet | ja |  |
| `POST` | `/invoices/{invoice_id}/versenden` | angemeldet | ja | Versandlimit je Mandant (30/h, 100/Tag), Reply-To |
| `POST` | `/invoices/{invoice_id}/zugferd-pdf` | angemeldet | ja |  |
| `GET` | `/kassenbuch` | angemeldet | ja |  |
| `POST` | `/kassenbuch` | angemeldet | ja |  |
| `GET` | `/kontakte` | angemeldet | ja |  |
| `POST` | `/kontakte` | angemeldet | ja |  |
| `DELETE` | `/kontakte/{kontakt_id}` | angemeldet | ja |  |
| `PATCH` | `/kontakte/{kontakt_id}` | angemeldet | ja |  |
| `POST` | `/kontakte/{kontakt_id}/archivieren` | angemeldet | ja |  |
| `GET` | `/kontakte/{kontakt_id}/historie` | angemeldet | ja |  |
| `POST` | `/kontakte/{kontakt_id}/wiederherstellen` | angemeldet | ja |  |
| `GET` | `/lieferscheine` | angemeldet | ja |  |
| `POST` | `/lieferscheine` | angemeldet | ja |  |
| `GET` | `/lieferscheine/{lieferschein_id}` | angemeldet | ja |  |
| `GET` | `/lieferscheine/{lieferschein_id}/pdf` | angemeldet | ja |  |
| `GET` | `/lohn/mitarbeitende` | **Owner** | ja | Gehaltsdaten Dritter: nur Owner (gesamter Router /lohn) |
| `POST` | `/lohn/mitarbeitende` | **Owner** | ja |  |
| `PATCH` | `/lohn/mitarbeitende/{mitarbeiter_id}` | **Owner** | ja |  |
| `POST` | `/lohn/mitarbeitende/{mitarbeiter_id}/deaktivieren` | **Owner** | ja |  |
| `POST` | `/lohn/mitarbeitende/{mitarbeiter_id}/reaktivieren` | **Owner** | ja |  |
| `GET` | `/lohn/monate/{jahr}/{monat}/export` | **Owner** | ja |  |
| `GET` | `/lohn/monatsentwuerfe` | **Owner** | ja |  |
| `POST` | `/lohn/monatsentwuerfe` | **Owner** | ja |  |
| `PATCH` | `/lohn/monatsentwuerfe/{entwurf_id}` | **Owner** | ja |  |
| `POST` | `/lohn/monatsentwuerfe/{entwurf_id}/abschliessen` | **Owner** | ja |  |
| `GET` | `/lohn/monatsentwuerfe/{entwurf_id}/lohnzettel` | **Owner** | ja |  |
| `POST` | `/lohn/monatsentwuerfe/{entwurf_id}/reaktivieren` | **Owner** | ja |  |
| `GET` | `/mahnungen` | angemeldet | ja |  |
| `GET` | `/mahnungen/{mahnung_id}/pdf` | angemeldet | ja |  |
| `POST` | `/mahnungen/{mahnung_id}/versenden` | angemeldet | ja | Versandlimit je Mandant (30/h, 100/Tag), Reply-To |
| `GET` | `/positionskategorien` | angemeldet | ja |  |
| `DELETE` | `/positionskategorien/{kategorie_id}` | angemeldet | ja |  |
| `GET` | `/produkte` | angemeldet | ja |  |
| `POST` | `/produkte` | angemeldet | ja |  |
| `PATCH` | `/produkte/{produkt_id}` | angemeldet | ja |  |
| `GET` | `/produkte/{produkt_id}/lagerbewegungen` | angemeldet | ja |  |
| `POST` | `/produkte/{produkt_id}/lagerbewegungen` | angemeldet | ja |  |
| `GET` | `/security` | angemeldet | ja |  |
| `POST` | `/security/email/aenderung-bestaetigen` | angemeldet | ja |  |
| `POST` | `/security/email/aenderung-starten` | angemeldet | ja | Passwort, Fehlversuchszähler, 5 Mails/h pro Konto |
| `POST` | `/security/mfa/deaktivieren` | angemeldet | ja | Passwort + Code (TOTP oder Wiederherstellungscode), Fehlversuchszähler, Replay-Schutz, beendet alle Sitzungen, löscht die Wiederherstellungscodes; **für Rollen mit MFA-Pflicht gesperrt (403)** |
| `POST` | `/security/mfa/einrichten` | angemeldet | ja |  |
| `POST` | `/security/mfa/neu-einrichten` | angemeldet | ja | Passwort + Code (TOTP oder Wiederherstellungscode), Fehlversuchszähler, Replay-Schutz |
| `POST` | `/security/mfa/neu-einrichten/bestaetigen` | angemeldet | ja | bei der ersten Aktivierung einmalig 10 Wiederherstellungscodes in der Antwort |
| `POST` | `/security/mfa/wiederherstellungscodes/neu` | angemeldet | ja | Passwort + aktueller Code (TOTP oder Wiederherstellungscode), Fehlversuchszähler; alle alten Codes werden ungültig |
| `POST` | `/security/sessions/andere-abmelden` | angemeldet | ja |  |
| `POST` | `/security/sessions/{session_id}/abmelden` | angemeldet | ja | nur eigene Sitzungen |
| `GET` | `/stammdaten/importe` | **Owner** | ja |  |
| `POST` | `/stammdaten/importe/{import_id}/rueckgaengig` | **Owner** | ja |  |
| `GET` | `/stammdaten/{ziel}/export` | **Owner** | ja |  |
| `POST` | `/stammdaten/{ziel}/import` | **Owner** | ja |  |
| `POST` | `/stammdaten/{ziel}/import/fehlerliste` | **Owner** | ja |  |
| `POST` | `/stammdaten/{ziel}/import/pruefen` | **Owner** | ja |  |
| `POST` | `/stammdaten/{ziel}/import/vorschau` | **Owner** | ja |  |
| `GET` | `/stammdaten/{ziel}/vorlage` | **Owner** | ja |  |
| `POST` | `/suche` | angemeldet | ja | durchsucht nur den eigenen Mandanten |
| `GET` | `/umzug` | angemeldet | ja |  |
| `GET` | `/wiederkehrende-ausgaben` | angemeldet | ja |  |
| `POST` | `/wiederkehrende-ausgaben` | angemeldet | ja |  |
| `POST` | `/wiederkehrende-ausgaben/erzeugen` | angemeldet | ja |  |
| `POST` | `/wiederkehrende-ausgaben/{vorlage_id}/deaktivieren` | angemeldet | ja |  |
| `GET` | `/wiederkehrende-rechnungen` | angemeldet | ja |  |
| `POST` | `/wiederkehrende-rechnungen` | angemeldet | ja |  |
| `POST` | `/wiederkehrende-rechnungen/erzeugen` | angemeldet | ja |  |
| `POST` | `/wiederkehrende-rechnungen/{vorlage_id}/deaktivieren` | angemeldet | ja |  |

## So wird die Matrix neu erzeugt / geprüft

- `cd backend && pytest tests/test_autorisierung.py tests/test_mandantentrennung.py` (SQLite) bzw.
  `scripts/rls_testlauf.sh -q tests/test_autorisierung.py tests/test_mandantentrennung.py` (Postgres, Laufzeitrolle ohne BYPASSRLS).
- `test_autorisierung.py` prüft zusätzlich, dass die früher tarifgesperrten Lese-Routen jedem Mandanten offenstehen (kein HTTP 402).
- Grenze: Die Tests zeigen, dass Fremdzugriffe abgewiesen werden und dass die Rollen/Gates wie festgelegt wirken. Sie beweisen
  nicht, dass die Festlegung fachlich vollständig ist (siehe "Offen" oben).
