# Bilantiq: Sicherheitsarbeiten für Claude

Stand: 22. Oktober 2026. Repository: https://github.com/Kayvooo/bilantiq
Review-Basis: `c63413a74bea1af2570dd0121b144202d2f9c7db`.

## Auftrag

Setze die unten Claude zugeordneten Sicherheitsänderungen in kleinen, überprüfbaren PRs um. Lies zuerst `AGENTS.md`,
`CLAUDE.md`, `CONTRIBUTING.md`, `docs/autorisierungs-matrix.md` und die jeweiligen Specs. Prüfe den aktuellen Branch:
Der Review beschreibt den genannten Commit, nicht automatisch einen späteren Stand. Verifiziere jeden Befund erneut.

Das Produkt bleibt eine selbst gehostete Open-Source-Buchhaltung ohne zwingende Cloud-Dienste. Bestehende Geschäftsdaten,
Schlüssel und Buchungshistorien müssen erhalten bleiben. Neue Schemaänderungen ausschließlich als neue Migrationen.

## Aufteilung und Reihenfolge

| Paket | Verantwortung | Ergebnis |
| --- | --- | --- |
| F1: Migration/API-Datenbankrechte trennen | Codex | Separater Migrator, unprivilegierte API, Startprüfung, Upgrade-Anleitung und Tests |
| F2/F3: Berechtigungen und MFA | Claude, zuerst | Rollen-/Rechtespec, Backend und UI, Negativtests und Datenmigration |
| F4: Dokumentverarbeitung isolieren | Claude, danach | Isolierte Worker und begrenzte Aufträge; kurzfristig Ressourcenlimits |
| F5: Schlüssel-Lebenszyklus | Claude | Audit-Schlüsseltrennung, versionierte HMAC-Rotation, Erhalt alter Daten |
| F6: Audit und Sicherheitserkennung | Claude | Zuverlässige Ereignisse, getrennte Ablage und datensparsame Alarmierung |
| F7: Vollständiger Restore-Nachweis | Codex: Abnahmeplan; Claude: nötige Anwendungshilfen | Wiederherstellung mit Schlüsseln, Dateien und fachlichen Prüfungen |
| F8: CI/Lieferkette und Betriebsanleitungen | Codex | Fehler werden sichtbar/blockierend; Deployment-/Integrationsprüfungen |
| Fachreview und Zusammenführung | Codex nach Vorliegen der Claude-PRs | Prüfung gegen Abnahmekriterien und offene Risiken |

Codex arbeitet auf `security/runtime-isolation`. Starte Claude-Pakete nach Übernahme dieser Änderungen auf separaten
Branches. Die F1-Dateien sind unter anderem Compose, Dockerfile, Secret-Erzeugung, Laufzeitprüfung, Migrator und
Deployment-Workflow. Stimmen spätere Änderungen nicht mehr mit dieser Aufteilung überein, dokumentiere sie im PR.

## F2: zentrale, feinere Autorisierung

### Beleg und Ursache

`owner`/`mitglied` ist zu grob für getrennte Arbeitsaufgaben. `backend/app/reports/routes.py` erlaubt DATEV-Export bereits
mit `require_full_auth`; Mitglieder können Bankimporte durchführen, Rechnungen stornieren und Buchhaltungseinstellungen
ändern. Lohnvorbereitung und umfassender Datenexport sind bereits Owner-only. Diese Kontrollen erhalten.

### Umsetzungsauftrag

1. Erstelle `docs/specs/sicherheitsrollen.md` mit einer expliziten Aktion-/Rollenmatrix. Schlage Rollen für Inhaber,
   Buchhaltung, Erfassung und Lesen vor; die technische Prüfung soll über benannte Rechte erfolgen.
2. Prüfe Rechte zentral im Backend, bei jedem Aufruf. Der Mandant stammt weiter aus der validierten Sitzung;
   Rechteänderungen müssen sofort auf bestehende Sitzungen wirken. UI-Sichtbarkeit ergänzt diese Prüfung.
3. Trenne insbesondere Stammdaten-/IBAN-Änderung, Benutzerverwaltung, Export, Storno, Freigabe und Belegerfassung.
   Lege auch für Lesen, PDF-/Originaldownload, Suche und KI-Zugriffe Rechte fest.
4. Migriere bestehende Mitglieder mit einem erklärten, kompatiblen Verfahren. Eine automatische Verschärfung darf
   keine Instanz unbemerkt unbedienbar machen. Letzter Owner darf nicht ersatzlos entfernt/anonymisiert werden.
5. Aktualisiere Autorisierungsmatrix, UI und sämtliche betroffenen Tests.

### Abnahme

- Für jede Rechteklasse: erlaubter Zugriff, verweigerter Zugriff und fremder Mandant getestet.
- Manipulierte/alte Rollenangaben im Token ändern keine Rechte.
- Rechteentzug wirkt ohne erneute Anmeldung; direkte API-Aufrufe sind genauso geschützt wie UI-Aktionen.
- Finanz- und Personaldaten erscheinen weder in Fehlermeldungen noch in Protokollen.

## F3: MFA-Pflicht und erneute Bestätigung sensibler Aktionen

### Beleg und Ursache

`backend/app/auth/routes.py::_ohne_mfa_anmelden` erstellt volle Sitzungen ohne MFA. Die vorhandene TOTP-Implementierung
hat Replay-Schutz, Wiederherstellungscodes und serverseitigen Sitzungswiderruf. Diese Mechanismen wiederverwenden.

### Umsetzungsauftrag

- MFA für Owner verbindlich machen. Für andere Rollen eine serverseitige, klar dokumentierte Richtlinie vorsehen.
- Bestehende Owner benötigen einen sicheren Einrichtungsweg: begrenzter Onboarding-Scope statt voller Fachrechte.
- Für IBAN-Änderungen, privilegierte Benutzeränderungen und sensible Gesamtexporte eine frische Bestätigung verlangen.
  Definiere ein kurzes Gültigkeitsfenster und binde die Bestätigung an Konto/Sitzung/Aktionsklasse.
- Recovery darf die Richtlinie nicht unbeabsichtigt umgehen. Serverbasierte Notfallwiederherstellung ist eine eigene,
  protokollierte Betreiberfunktion. Einzige Inhaber dürfen nicht ohne nachvollziehbaren Wiederherstellungsweg stranden.
- Die 30-Tage-Option „Gerät merken“ ist aktuell eine lange Sitzung; behandle sie nicht als frische MFA-Bestätigung.

### Abnahme

- Owner ohne MFA erhält nur Einrichtungsmöglichkeiten; fachliche API-Endpunkte bleiben gesperrt.
- Abgelaufene oder sitzungsfremde Bestätigungen werden verworfen; TOTP-/Recovery-Replay bleibt gesperrt.
- Tests für erstmalige Einrichtung, Bestandsupgrade, Geräteverlust, Sitzungswiderruf und privilegierte Aktion.

## F4: Dokumentparser isolieren und Ressourcen begrenzen

### Beleg und Ursache

`backend/app/receipts/service.py` verarbeitet Dokumente synchron im API-Kontext. Poppler/Tesseract laufen im selben
Container wie Datenbankzugang und Entschlüsselungsschlüssel. `ai_extraction.py` besitzt PDF-Seiten-/Pixellimits und
Render-Timeouts; dem Tesseract-Aufruf fehlt eine explizite Laufzeitgrenze. Sichere XML-Verarbeitung ist bereits vorhanden.

### Kurzfristiger PR

- Tesseract-Timeout, Gesamtbudget pro Auftrag, Parallelitätsgrenze und begrenzte Warteschlange.
- Frühes Request-Body-Limit am Proxy und API-Eingang mit Rücksicht auf Multipart-Overhead; weiterhin Limits je Datei.
- Gleiche Grenzen für Belege, Bank-/Stammdatenimporte, Altrechnungen und Vorschauen prüfen.
- Nach Überschreitung: Prozesse/Temporärdateien aufräumen, verständlicher Status, kein Verlust gespeicherter Originale.

### Architektur-PR

- Worker als eigene Sicherheitsdomäne: kein allgemeiner DB-Zugang, kein vollständiger Schlüsselbund, keine
  SMTP-Geheimnisse, kein ausgehender Internetzugang. Nur auftragsbezogene Daten und eng begrenzte Ergebnisse.
- Untrusted Uploads zunächst in Quarantäne; Ergebnisprüfung und endgültige Buchungsentscheidung verbleiben in der API.
- Definiere Job-ID, Mandantenbindung, Idempotenz, Wiederholungen, Abbruch und Zustandswechsel. Auftragsergebnisse dürfen
  ausschließlich zum berechtigten Mandanten gelangen.
- CPU/RAM/PIDs/Laufzeit und Queue-Länge technisch begrenzen. Buchhaltungsfunktionen müssen bei Worker-Ausfall weiterlaufen.

### Abnahme

Robustheitstests mit ungültigen/grenzwertigen Dateien, Zeitüberschreitung, parallelen Aufträgen, Neustarts und zwei
Mandanten. Nachweisen, dass blockierte OCR weder die API vollständig belegt noch dauerhafte DB-Sperren zurücklässt.

## F5: Schlüsselrotation ohne Datenverlust

### Beleg und Ursache

`backend/scripts/rotate_encryption.py` überspringt PostgreSQL-Audit-Kontexte wegen des Append-only-Triggers. Alte Keys
bleiben nötig. `EMAIL_LOOKUP_SECRET` und `BLIND_INDEX_SECRET` besitzen kein vollständiges Rotationsverfahren. Die
Feldverschlüsselung unterstützt bereits versionierte AES-GCM-Envelope-Schlüssel.

### Umsetzungsauftrag

- Schreibe zuerst eine Spec für Audit-Schlüssel und eine getrennte Spec für Such-/HMAC-Schlüssel.
- Ein Audit-Archiv erhält einen separaten Schlüssel-Lebenszyklus. Möglich: unveränderlicher signierter Ereignisinhalt
  und getrennte, kontrolliert umschlüsselbare Schlüsselumschläge; Integritätsnachweis und Zugriffstrennung bleiben nötig.
- Alte Audit-Daten dürfen weder gelöscht noch unter einem entfernten Schlüssel unlesbar gemacht werden.
- HMAC-Rotation versionieren: während der Migration beide Versionen lesen, neue schreiben, Bestände kontrolliert
  neu indizieren, Eindeutigkeit/Duplikaterkennung erhalten, vollständigen Abschluss prüfen.
- Prüfe alle Verwendungen: Login-E-Mail, IBANs, Bankduplikate, Altrechnungen, MFA-Recovery und Reset-/Bestätigungstoken.
  Bereits ausgestellte kurzlebige Token benötigen eine explizite Übergangsregel.
- Wiederanlauf, Unterbrechung, Backups mit alten Keys und Ausfall des Schlüsselmaterials gehören zum Verfahren.

### Abnahme

Ein Testbestand mit mindestens zwei Mandanten, mehreren Key-Versionen und Audit-Einträgen bleibt nach Rotation und
Restore lesbar. Unterbrochene Rotation ist fortsetzbar. Kein alter Schlüssel wird entfernt, solange Bestände oder
aufzubewahrende Backups davon abhängen. Kein Produktiv-Key in Testdaten oder Logs.

## F6: Audit und Erkennung

- Zentralen Ereigniskatalog festlegen: Konto-/MFA-/Rollenänderungen, Widerruf, sensible Exporte, kritische Stammdaten,
  Freigaben/Stornos sowie relevante verweigerte Zugriffe. Für Lesezugriffe Datenminimierung und Volumen abwägen.
- Fachänderung und Audit-Ereignis atomar persistieren. Eine Transactional Outbox kann den zuverlässigen Versand in
  eine separat administrierte Ablage übernehmen. Duplikate sind erkennbar; nach Ausfällen wird aufgeholt.
- Nur pseudonyme Konto-/Mandanten-/Sitzungsreferenzen und Ereignismetadaten übertragen. Keine Rechnungstexte,
  Zugangstoken, Passwörter oder entschlüsselten Finanzfelder. IP-Adressen nur mit bewusstem Aufbewahrungskonzept.
- Lokale, selbst hostbare Auswertung/Benachrichtigung anbieten; Ausfall der optionalen Alarmablage begrenzt puffern.
- Aktuelle Dokumentation korrigieren: IP-Limits existieren bereits, liegen aber pro Prozess im Speicher.
- Abnahme: Transaktionsrollback, erneute Zustellung, Sammlerausfall, Zugriffstrennung und tatsächlich empfangener Testalarm.

## F7: Anwendungshilfen zur Restore-Abnahme

Codex definiert den Betriebslauf. Ergänze nötigenfalls ein separat ausführbares, nur lesendes Prüfkommando mit
anonymem Ergebnisbericht: Schlüsselversionen vorhanden, ausgewählte verschlüsselte Spalten lesbar, Dateireferenzen
auflösbar und entschlüsselbar, Mandantenbindung/Hashes korrekt. Es darf keine Klartextdaten ausgeben oder unbemerkt
Migrationen/Schlüsselwechsel durchführen. Vollständigen Restore ausschließlich in einer isolierten Testinstanz ausführen.

## Arbeitsregeln und Validierung

1. Je Paket ein kleiner PR mit Problem, Verhalten, Migration, Rückweg und verbleibenden Risiken.
2. Vorhandene Sicherheitskontrollen beibehalten: RLS plus Mandantenfilter, Argon2id, AES-GCM, widerrufbare Sitzungen,
   sichere XML-Parser, TOTP-Replay-Schutz, Append-only-Audit und verschlüsselte Backups.
3. `cd backend && pytest -q`; bei RLS/Auth/Krypto zusätzlich PostgreSQL mit tatsächlicher unprivilegierter Laufzeitrolle.
4. Bei Frontendänderungen `npx tsc -b --noEmit`, `npm run lint`, `npm run build`.
5. Schema: genau ein Alembic-Head; Upgrade und Datenbestand prüfen. Vorhandene Migrationen nicht umschreiben.
6. Neue Sicherheitsfunktion braucht einen Regressionstest, der ohne sie fehlschlägt. Ergänzend echte Compose-Integration.
7. Testergebnisse mit Umgebung und übersprungenen Prüfungen berichten. Konfiguration, statische Prüfung und echter
   Lauf sind unterschiedliche Nachweise. Keine Aussage „sicher“, „konform“ oder „Release-fertig“ ohne den passenden Beleg.

## Übergabe an Codex

Liefere PR-/Branch-Links, Commit-SHAs, geänderte Specs, Testresultate, Migrations-/Rollback-Anweisungen und Restpunkte.
Codex prüft anschließend Autorisierung, Mandantentrennung, Privilegien, Schlüssel-Lebenszyklus und Fehlerfälle. Produktiver
Rollout, echte Backups und Server-/DNS-/VPN-/GitHub-Kontoeinstellungen benötigen die konkrete Betriebsumgebung.

## Einordnung des Reviews

Dies ist ein defensiver Arbeitsauftrag aus einer statischen Architekturprüfung. Ein Superuser im Standarddeployment
belegt den Verlust der RLS-Schutzschicht, nicht einen bereits erfolgten Datenabfluss. Rollen- und MFA-Risiken hängen
auch davon ab, ob die Instanz öffentlich, über VPN oder mit mehreren Personen betrieben wird. Bei vollständiger
Kompromittierung des Backends schützt anwendungsseitig gesetzter RLS-Kontext nicht unabhängig vor Mandantenwechseln.
