# Bilantiq Incident-Plan: Datenpannen und Sicherheitsvorfälle

Stand: 14. Oktober 2026

> **Kein Rechtsrat.** Dieses Dokument ist eine technische und organisatorische Arbeitsvorlage. Ob
> eine Meldung nach Art. 33 DSGVO nötig ist, wer Verantwortlicher ist und was in einer
> Benachrichtigung stehen muss, bewertet eine Datenschutz-Fachperson bzw. ein Anwalt. Die Textvorlagen
> unten sind Platzhalter, keine geprüften Rechtstexte. Alle Felder in `[eckigen Klammern]` müssen
> vor dem Ernstfall ausgefüllt werden.

Rollen vorab klären: Das Bilantiq-Projekt betreibt keinen Dienst und verarbeitet keine Daten Dritter. Wer eine Instanz
betreibt, ist für deren Daten in der Regel selbst Verantwortlicher im Sinne der DSGVO (bei einer Instanz für fremde Firmen
kann der Betreiber Auftragsverarbeiter nach Art. 28 DSGVO sein; dann gilt Art. 33 Abs. 2 und ein AV-Vertrag legt die Fristen
fest). Diese Einordnung ist im Einzelfall rechtlich zu prüfen.

## 0. Ansprechpartner (vor dem Start ausfüllen)

| Rolle | Name | Telefon (erreichbar rund um die Uhr) | E-Mail | Vertretung |
| --- | --- | --- | --- | --- |
| Incident-Leitung (Entscheidungen) | [Name] | [Nummer] | [Adresse] | [Name] |
| Technik (Server, Backups, Keys) | [Name] | [Nummer] | [Adresse] | [Name] |
| Datenschutz (DSB oder externe Beratung) | [Name] | [Nummer] | [Adresse] | [Name] |
| Rechtsberatung | [Kanzlei] | [Nummer] | [Adresse] | |
| Hoster / Provider-Support | [Anbieter] | [Nummer] | [Ticket-URL] | |
| Zuständige Aufsichtsbehörde | [Behörde laut Firmensitz] | | [Meldeportal-URL] | |
| Cyber-Versicherung (falls vorhanden) | [Versicherer] | [Notfallnummer] | | Police: [Nr.] |

Der Zugang zu diesen Informationen darf nicht nur auf dem betroffenen Server liegen (Notfallzugang:
`docs/betrieb-runbook.md`, Abschnitt 1).

## 1. Die 72-Stunden-Uhr

Art. 33 Abs. 1 DSGVO: Meldung an die Aufsichtsbehörde **unverzüglich und möglichst binnen 72 Stunden**,
nachdem die Panne bekannt wurde, es sei denn, sie führt voraussichtlich nicht zu einem Risiko für
die Betroffenen. Die Frist beginnt mit der Kenntnis, nicht mit dem Eintritt. Jede Verzögerung ist zu
begründen, Informationen dürfen schrittweise nachgereicht werden (Art. 33 Abs. 4).

Sofort bei Verdacht festhalten (Vorfallsprotokoll, Abschnitt 8):

- **T0:** Zeitpunkt, zu dem jemand im Team von dem Verdacht erfahren hat: `[Datum, Uhrzeit, Zeitzone]`
- **Frist (T0 + 72 h):** `[Datum, Uhrzeit]`
- Auch Nicht-Meldungen werden dokumentiert (Art. 33 Abs. 5): Was war, wie wurde das Risiko bewertet,
  warum wurde nicht gemeldet.

## 2. Erkennung: Woher kommt ein Verdacht?

Was Bilantiq tatsächlich liefert und was nicht. Das ist die ehrliche Grundlage jeder Bewertung.

**Quellen**

| Quelle | Was sie zeigt | Grenze |
| --- | --- | --- |
| Audit-Log (Tabelle `audit_log_eintraege`, append-only) | `registrierung`, `login_erfolgreich`, `login_fehlgeschlagen`, `mfa_code_falsch`, `mfa_aktiviert`, `mfa_deaktiviert`, `mfa_neu_eingerichtet`, `mfa_wiederherstellungscodes_erzeugt`, `mfa_wiederherstellungscodes_erneuert`, `mfa_wiederherstellungscode_verwendet`, `mfa_wiederherstellungscode_falsch`, `passwort_geaendert`, `passwort_reset_angefordert`, `passwort_reset_abgelehnt`, `passwort_zurueckgesetzt`, `email_aenderung_gestartet`, `email_geaendert`, `sitzung_erstellt`, `sitzung_abgemeldet`, `andere_sitzungen_abgemeldet`, `mitglied_direkt_angelegt`, `mitglied_entfernt`, `einladung_erstellt`, `datenexport`, `stammdaten_export`, `stammdaten_import`, `loeschantrag` sowie fachliche Aktionen (Rechnung, Beleg, Bank, Lohn) | Speichert Mandant, Nutzer, Aktion, Zeit und einen verschlüsselten Kontext. **Keine IP-Adresse.** **Lesezugriffe** (wer hat welche Rechnung angesehen) werden nicht protokolliert, nur Schreib-/Sicherheitsaktionen und Exporte. Ein reiner Lese-Datenabfluss über ein gültiges Token ist im Audit-Log nicht erkennbar. |
| Seite „Sicherheit & Datenschutz“ (API `/security`) | Aktive Sitzungen des Kontos mit verschlüsselt gespeichertem User-Agent | Nur für den Nutzer selbst, keine IP |
| Caddy-Container-Log | Laufzeit-/Fehlermeldungen, TLS-Zertifikatsereignisse | Im aktuellen `Caddyfile` ist **kein `log`-Block** für Zugriffsprotokolle konfiguriert. Es gibt also keine Caddy-Access-Logs mit IP-Adressen, sofern das nicht ergänzt wurde. |
| Backend-Container-Log (uvicorn) | Zugriffszeilen mit Client-IP (über `--proxy-headers`), Methode, Pfad, Status; Python-Tracebacks bei Serverfehlern | Anwendungscode schreibt selbst keine Logs (`logging`/`print` kommen in `backend/app` nicht vor). Siehe Warnung zu sensiblen Pfaden in `docs/betrieb-runbook.md`, Abschnitt 2. |
| Postgres-Log | Fehler, Verbindungsprobleme | Standardkonfiguration, keine Statement-Protokollierung eingerichtet |
| Monitoring/Alarm | Erreichbarkeit, Zertifikat, Platte, Backup-Fehler | Muss erst aufgesetzt werden |
| Hinweise von außen | Nutzermeldung, Provider-Mitteilung, Sicherheitsforscher | Support-Postfach `[Adresse]` täglich prüfen (Hypercare) |

**Typische Indikatoren (Prüfliste)**

- Häufung von `login_fehlgeschlagen` / `mfa_code_falsch` für ein Konto oder viele Konten
  (Konto-Sperre nach 5 Fehlversuchen für 15 Minuten, `failed_login_limit` / `failed_login_lock_minutes`;
  ein Schutz pro IP existiert im Code nicht).
- `mfa_deaktiviert`, `passwort_geaendert`, `passwort_zurueckgesetzt`, `email_geaendert` ohne Wissen des Nutzers; `mfa_wiederherstellungscode_verwendet` (ein Wiederherstellungscode wurde zur Anmeldung genutzt, bei unbekanntem Anlass wie ein Gerätverlust-Verdacht behandeln); gehäufte `passwort_reset_angefordert` für ein Konto (Postfach-Übernahme oder Belästigung).
- `datenexport` oder `stammdaten_export` zu ungewöhnlicher Zeit; `mitglied_direkt_angelegt` /
  `einladung_erstellt`, die der Inhaber nicht kennt.
- Unbekannte Sitzungen auf der Sicherheitsseite eines Kontos.
- Unerwartete `permission denied`-Meldungen oder Mandanten-Verwechslungen in Logs/Support-Fällen
  (Verdacht auf RLS-Fehler, das wäre ein schwerer Vorfall: Abschnitt 6, Szenario C).
- Fehlgeschlagene Backups, unerwartete Änderungen im Backup-Verzeichnis oder am Secrets-Ordner.

## 3. Sofortmaßnahmen: Eindämmen

Ziel: weiteren Schaden stoppen, ohne Beweise zu zerstören. **Zuerst sichern (Abschnitt 5), dann
verändern, soweit der Schaden nicht weiter wächst.** Nichts löschen, nichts „aufräumen“.

Je nach Lage (Reihenfolge anpassen):

1. **Betroffene Konten sperren/Sitzungen beenden.**
   - Nutzer selbst: „Andere Sitzungen abmelden“ (markiert die übrigen Sitzungen als widerrufen) oder
     Passwort/E-Mail/MFA ändern (erhöht zusätzlich `security_version` und widerruft alle Sitzungen).
   - Alle Sitzungen aller Nutzer: `JWT_SECRET` ersetzen und Backend neu starten; alle bestehenden
     Tokens sind dann ungültig, jeder muss sich neu anmelden (Details und Nebenwirkungen:
     Abschnitt 7). Alternativ mit Administratorzugang zur Datenbank Sitzungen als widerrufen markieren
     (Spalte `auth_sessions.widerrufen_am`; **nicht getestet**, vorher auf einer Testinstanz prüfen).
2. **Angriffsfläche verkleinern.** `REGISTRATION_MODE=closed` setzen bzw. den Reverse-Proxy anhalten (siehe
   `docs/rollback.md`, Schritt 0).
3. **Netz abschotten.** Provider-Firewall auf 80/443 plus nur Admin-IP für SSH
   (`docs/security-production.md`, Abschnitt 1). PostgreSQL ist im Compose-Stack nur im internen
   Docker-Netz (`backend_internal`) erreichbar. Wenn ein Host kompromittiert ist: Server
   isolieren (Provider-Konsole, Netzwerk trennen), **nicht ausschalten**, solange Speicher/Logs noch
   gesichert werden müssen.
4. **Zugangsdaten rotieren**, die im Verdachtsfall betroffen sein können (Abschnitt 7).
5. **Kompromittierten Code-/Image-Stand ausschließen:** laufendes Image gegen den Git-Tag
   vergleichen, Images neu bauen (`docker compose ... build`), Abhängigkeiten prüfen.

## 4. Bewertung: Was ist passiert, welches Risiko besteht?

Für das Protokoll (Abschnitt 8) und die Entscheidung über Meldung/Benachrichtigung:

1. **Art der Verletzung:** Vertraulichkeit (Unbefugter Zugriff/Abfluss), Integrität (Daten verändert),
   Verfügbarkeit (Daten weg/unzugänglich)? Mehrere möglich.
2. **Betroffene Mandanten und Personen:** Über `mandant_id` im Audit-Log eingrenzen. Wer sind die
   Betroffenen: Nutzer/Mitarbeiter von Kunden, Kunden-Kontakte (Rechnungsempfänger), Mitarbeitende in
   der Lohnvorbereitung?
3. **Betroffene Datenkategorien** (Tabelle in `docs/dsgvo-toms-entwurf.md`): Konto-E-Mail und
   Passwort-Hash, MFA-Secret, Firmen- und Steuerdaten, Kontakte (Name, Adresse, IBAN, E-Mail),
   Rechnungen/Belege/Bankumsätze, Lohnvorbereitung (Name, Personalnummer, Brutto), hochgeladene Dateien.
4. **Was war verschlüsselt, was nicht?**
   - Application-Level-AES-256-GCM mit Envelope-Verschlüsselung: Firmenstammdaten, Kontakt- und
     Rechnungsfreitexte, Beträge, Bankdaten, Belegdateien, Logos, Briefpapier. Ein Abfluss **nur der
     Datenbank oder nur des Backups ohne die Schlüssel** legt diese Inhalte nicht offen.
   - **Nicht** application-level verschlüsselt (strukturiert für Reports/Suche): u. a. Datumsfelder,
     Mandanten-/Nutzer-IDs, Status, Rechnungsnummern-Kreise, Personalnummer, Eintritts-/Austrittsdatum. Die genaue Liste kommt aus den Modellen (`EncryptedText`/`EncryptedDecimal`).
   - Wurden die **Schlüssel** (`DATA_ENCRYPTION_KEYS`, `BLIND_INDEX_SECRET`, `JWT_SECRET`, ...) mit
     abgeflossen, gilt die Verschlüsselung als aufgehoben. Dann wie Klartext-Abfluss bewerten.
   - Passwörter liegen als Argon2id-Hash (ältere bcrypt-Hashes werden beim nächsten Login ersetzt).
5. **Risiko für Betroffene:** gering / Risiko / hohes Risiko (Abschnitt 1 und 5 des Art. 33/34).
   Kriterien: Art und Menge der Daten, Identifizierbarkeit, Schwere der Folgen (Betrug, Identitätsdiebstahl,
   finanzielle Schäden), Verschlüsselung, Dauer des Zugriffs. **Diese Einstufung trifft die
   Datenschutz-Fachperson, nicht die Technik allein.**
6. **Ursache und Ende:** Ist die Lücke geschlossen? Gibt es weitere betroffene Systeme?

## 5. Beweissicherung (vor Änderungen)

1. **Vorfallsprotokoll** anlegen und von Beginn an führen (Abschnitt 8).
2. **Audit-Log sichern.** Es ist append-only: In der Anwendung blockiert ein Session-Hook
   Update/Delete (`AuditLogAppendOnlyError`), auf Postgres verhindert zusätzlich ein Trigger jede
   Änderung (Migration 0001), und die Laufzeitrolle hat `UPDATE`, `DELETE`, `TRUNCATE` darauf entzogen
   (`backend/scripts/runtime_rolle.sql`). Trotzdem Kopie ziehen, mit Administratorzugang:
   `pg_dump -t audit_log_eintraege` in eine **verschlüsselte** Datei (`age`), Hashwert notieren.
   Der Kontext-Text ist AES-GCM-verschlüsselt, ohne die Keys (inklusive der **alten** Keys, siehe
   Abschnitt 7) ist die Kopie nicht auswertbar. Keys deshalb ebenfalls getrennt sichern.
3. **Container-Logs sichern, bevor Container neu gestartet oder ersetzt werden:**
   `docker compose --env-file .env.prod -f docker-compose.prod.yml logs --no-color --timestamps backend caddy postgres > vorfall-logs.txt`,
   danach `age`-verschlüsseln. Bei Compose-Standard-Logging (json-file ohne Rotation, siehe
   Runbook Abschnitt 2) können ältere Zeilen schon fehlen. Logs enthalten IP-Adressen und Pfade,
   entsprechend schützen.
4. **Frisches verschlüsseltes Backup** vom Ist-Zustand (`scripts/backup.sh`), getrennt vom regulären
   Backup-Bestand ablegen. Ältere Backups **nicht** durch die 14-Tage-Retention löschen lassen
   (`RETENTION_DAYS`, Standard 14), sondern den Vorfall-Zeitraum bewusst aufbewahren.
5. **Host-Evidenz:** Provider-Snapshot der VM, Auth-Log des Hosts (SSH), Docker-Events. Bei Verdacht auf
   Hostkompromittierung nicht selbst „reparieren“, sondern Snapshot ziehen und Fachleute hinzuziehen.
6. **SMTP:** Ereignisprotokolle beim SMTP-Anbieter exportieren.
7. Nichts davon in Chat-Tools, Tickets oder unverschlüsselte Ablagen kopieren, wenn es Zugangsdaten oder
   Kundendaten enthält.

## 6. Szenarien (Kurzanleitungen)

**A. Einzelnes Konto übernommen** (Passwort geleakt, Phishing)
Sitzungen beenden, Passwort zurücksetzen lassen (Nutzer nutzt „Passwort vergessen“; das beendet alle Sitzungen, lässt MFA aber
aktiv und sendet eine Benachrichtigung an das Postfach; ist das Postfach selbst übernommen, hilft das nicht, dann
Support-Prozess mit Rückfrage), bei Gerätverlust/Verdacht MFA neu einrichten und Wiederherstellungscodes erneuern, Audit-Log des Kontos
auswerten (Exporte, Mitglieder-Änderungen, ausgehende Rechnungen/Mahnungen per E-Mail). Gingen
Rechnungen oder Mahnungen vom Konto an Dritte, sind deren Empfänger ebenfalls zu betrachten.

**B. Datenbank-Dump oder Backup abgeflossen**
Wichtigste Frage: Waren die Keys dabei? Backups sind `age`-verschlüsselt (Abschnitt 6 der
`security-production.md`), Application-Level-Daten zusätzlich AES-GCM. Dumps ohne Secrets legen
Freitexte und Beträge nicht offen. Weiterhin lesbar sind unverschlüsselte Metadaten. Rotation einleiten
(Abschnitt 7), `age`-Backup-Schlüssel tauschen, Bewertung nach Abschnitt 4.

**C. Mandantentrennung durchbrochen** (Nutzer sieht Daten eines anderen Mandanten)
Schwerer Vorfall, sofort Registrierung/Anmeldung sperren (Wartungsmodus), Fall reproduzieren,
Laufzeitrolle prüfen (`bilantiq_runtime` ohne `BYPASSRLS`, `docs/server-rollout.md`), RLS-Testlauf auf Staging
wiederholen (`backend/scripts/rls_testlauf.sh`). Betroffene Mandanten über Audit-Log und
Support-Meldung bestimmen. Meldepflicht prüfen lassen.

**D. Secrets/Keys im Repository oder in Logs gefunden**
Als abgeflossen behandeln: rotieren (Abschnitt 7), Git-Historie mit `gitleaks` prüfen.
Ein Entfernen aus der Historie genügt nicht.

**E. Host/Server kompromittiert**
Isolieren, Snapshot, alle Secrets des Hosts als abgeflossen betrachten, Neuaufbau auf frischem Host aus
Git-Tag und verschlüsseltem Backup (Abschnitt 9), alle Keys rotieren.

**F. Verfügbarkeitsverlust/Ransomware**
Wiederherstellung aus verschlüsseltem Off-site-Backup (Abschnitt 9). Beachten: Der private
`age`-Schlüssel liegt bewusst **nicht** auf dem Server. Ist das Backup verschlüsselt und wiederherstellbar, kann es
sein, dass keine Daten abgeflossen sind. Verfügbarkeitsverlust ist trotzdem eine Verletzung (Art. 4 Nr. 12).

**G. Dienstleister meldet Vorfall** (Hoster, SMTP, Backup-Speicher)
Wie ein eigener Vorfall behandeln: T0 ist der Zeitpunkt, zu dem Bilantiq die Meldung erhält. AV-Vertrag
und Meldeweg prüfen.

## 7. Rotation von Schlüsseln und Secrets

Welche Secrets es gibt, steht in `docker-compose.prod.yml` (Abschnitt `secrets`) und
`scripts/init-secrets.sh`. Bevor ein Wert getauscht wird: frisches verschlüsseltes Backup,
Key-Dateien getrennt sichern. Eine Rotation ist **nicht** bei jedem Secret folgenlos:

| Secret | Wirkung bei Austausch | Vorgehen / Grenze |
| --- | --- | --- |
| `jwt_secret` | Alle Sitzungs-Tokens werden ungültig, alle melden sich neu an. Keine Datenwirkung. | Datei ersetzen, Backend neu starten. Schnellster Weg, alle Sitzungen zu beenden. |
| `data_encryption_keys` (+ `DATA_ENCRYPTION_ACTIVE_KID`) | Neue Werte werden mit dem aktiven Key geschrieben. Bestandsdaten bleiben auf dem alten Key, bis rotiert wird. | Ablauf in `backend/scripts/rotate_encryption.py`: neuen Key **zusätzlich** aufnehmen, aktive KID setzen, Backend neu starten, Backup, Skript ausführen, danach `--pruefen`. **Alten Key nie vorschnell entfernen.** |
| `field_encryption_key` (Legacy-Fernet) | Nur für Altbestand relevant. Ein Verlust kann alte, noch nicht migrierte Werte unlesbar machen. | Nicht ersatzlos tauschen. Vor einer Entfernung prüfen, ob noch Fernet-Werte existieren (Migration 0029 hat sie migriert; nicht erneut verifiziert). |
| `email_lookup_secret` | Der HMAC-Lookup der Login-E-Mail (`users.email_lookup_hash`) hängt daran. Ein Tausch **bricht alle Logins**, solange die Hashes nicht neu berechnet werden. | **Es gibt kein Rotationsskript.** Nur mit einer eigens geschriebenen und an Staging getesteten Neuberechnung tauschen. Bei bestätigter Kompromittierung als Projekt planen, nicht als Handgriff. |
| `blind_index_secret` | Blind-Indizes für IBAN-Suche (Kontakte/Bank), Umsatz-Duplikaterkennung, Altrechnungsnummern und E-Mail-Änderungscodes. Tausch bricht Duplikaterkennung und Suche über diese Felder. | **Kein Rotationsskript.** Wie `email_lookup_secret`. |
| `postgres_password` / `database_url` | App kann sich nicht verbinden, wenn beide nicht übereinstimmen. | Gemeinsam rotieren (`docs/security-production.md`, Abschnitt 2); Laufzeitrolle `bilantiq_runtime` über `backend/scripts/runtime_rolle.sql` mit neuem Passwort neu setzen. |
| `smtp_password` | Versand von Rechnungen/Mahnungen schlägt fehl, bis der neue Wert gesetzt ist. | Beim Anbieter erneuern, Datei ersetzen, neu starten. |
| Backup-`age`-Schlüsselpaar | Neue Backups nutzen den neuen Public Key; alte Backups bleiben nur mit dem alten privaten Schlüssel lesbar. | Neues Paar erzeugen, `BACKUP_AGE_RECIPIENT` ändern, alten privaten Schlüssel aufbewahren, solange alte Backups gebraucht werden. |
| SSH-Schlüssel, Provider-Konto, Domain-/DNS-Konto | Zugriff auf die Infrastruktur. | Beim jeweiligen Anbieter, MFA aktivieren. |

**Bekannte Grenze (Postgres):** Das Audit-Log ist per Trigger append-only. Die Schlüsselrotation
kann es deshalb **nicht** auf den neuen Key umschreiben; es bleibt auf dem alten Key
(`rotate_encryption.py` meldet das). Folge: Der alte Key in `DATA_ENCRYPTION_KEYS` darf nie entfernt
werden, solange Audit-Einträge von ihm abhängen. War der alte Key kompromittiert, bleiben die Audit-Kontexte
bis dahin mit ihm entschlüsselbar. Auf SQLite (Entwicklung) gilt das nicht.

Nach jeder Rotation: Smoke-Test (Login, Rechnungsliste, PDF, Beleg-Download, Test-Mail),
Eintrag im Vorfallsprotokoll. Betrieblicher Ablauf: `docs/betrieb-runbook.md`, Abschnitt 4.

## 8. Meldung an die Aufsichtsbehörde (Art. 33)

Inhalt nach Art. 33 Abs. 3 (Grundlage für das Meldeformular der Behörde):

1. Art der Verletzung, soweit möglich Kategorien und ungefähre Zahl der Betroffenen und Datensätze.
2. Name und Kontaktdaten der DSB bzw. einer Anlaufstelle.
3. Wahrscheinliche Folgen.
4. Ergriffene oder vorgeschlagene Maßnahmen, auch zur Abmilderung.

**Vorfallsprotokoll (Vorlage)**

```
Vorfall-Nr.:                [JJJJ-NN]
Entdeckt von / am / um:     [Name] / [Datum] / [Uhrzeit, Zeitzone]          <- T0
Meldefrist (T0 + 72 h):     [Datum, Uhrzeit]
Beschreibung:               [Was wurde beobachtet?]
Betroffene Systeme:         [Caddy / Backend / Postgres / Backend-Volume / Secrets / SMTP / Backup]
Betroffene Mandanten (IDs): [mandant_id, ...]   (keine Klarnamen im Protokoll, wenn vermeidbar)
Datenkategorien:            [siehe docs/dsgvo-toms-entwurf.md]
Verschlüsselungsstatus:     [Keys betroffen? ja/nein/unbekannt]
Zeitliche Abfolge:          [HH:MM  Ereignis / Maßnahme / durchgeführt von]
Risikobewertung:            [gering / Risiko / hohes Risiko]  Begründung: [...]  Bewertet durch: [Name]
Meldung Aufsicht:           [ja/nein] am [Datum]  Aktenzeichen: [...]   Begründung bei Nein: [...]
Benachrichtigung Betroffene:[ja/nein] am [Datum]  Kanal: [...]
Benachrichtigung Kunden (Verantwortliche): [ja/nein] am [Datum]
Rotierte Secrets:           [Liste mit Datum]
Wiederherstellung:          [Backup-Datei, Datum, Restore-Ergebnis]
Ursache / Lessons Learned:  [...]
Abschluss:                  [Datum, verantwortlich]
```

## 9. Benachrichtigung der Betroffenen (Art. 34)

Nur bei **voraussichtlich hohem Risiko** für die Betroffenen, dann unverzüglich, in klarer Sprache:
Art der Verletzung, Kontaktstelle, wahrscheinliche Folgen, ergriffene Maßnahmen und Empfehlungen
(Art. 34 Abs. 2 i. V. m. 33 Abs. 3 lit. b-d). Ausnahmen (u. a. wirksame Verschlüsselung, Art. 34 Abs. 3)
bewertet die Datenschutz-Fachperson. Versand über den SMTP-Weg der App ist ungeeignet, wenn das
System kompromittiert ist; Absender und Kanal vorher festlegen: `[Kanal]`.

### Vorlage A: Information an Kunden (Verantwortliche), wenn Bilantiq Auftragsverarbeiter ist

```
Betreff: [Sicherheitsvorfall bei Bilantiq] Information gemäß Auftragsverarbeitungsvertrag

Guten Tag [Name],

wir informieren Sie über einen Sicherheitsvorfall, der Daten Ihres Kontos bei Bilantiq betrifft.

Was ist passiert: [Kurzbeschreibung, sachlich]
Zeitpunkt: [Beginn/Ende bzw. Entdeckung am ...]
Betroffene Daten: [Kategorien]
Betroffene Personen (ungefähr): [Anzahl/Gruppen]
Mögliche Folgen: [...]
Was wir getan haben: [Maßnahmen]
Was wir Ihnen empfehlen: [z. B. Passwort ändern, MFA aktivieren, auf Phishing achten]
Ihre mögliche Meldepflicht (Art. 33 DSGVO): Wir unterstützen Sie mit allen Angaben. Stand: [Datum].
Ansprechpartner: [Name, Telefon, E-Mail]

Weitere Informationen reichen wir nach, sobald sie vorliegen.
[Unterschrift]
```

### Vorlage B: Information an Betroffene (Art. 34)

```
Betreff: Wichtige Information zur Sicherheit Ihrer Daten bei Bilantiq

Guten Tag [Name],

am [Datum] haben wir festgestellt, dass [Kurzbeschreibung]. Betroffen sind folgende Angaben von Ihnen:
[Datenkategorien].

Mögliche Folgen für Sie: [...]
Das haben wir unternommen: [...]
Das empfehlen wir Ihnen: [...]
Bei Fragen erreichen Sie uns unter [Kontakt]. Zuständige Aufsichtsbehörde: [Behörde, Kontakt].

[Unterschrift]
```

### Vorlage C: Interne Kurzmeldung (Chat/Telefon-Eskalation)

```
INCIDENT [Nr.] - T0 [Zeit] - Frist [Zeit]
Lage: [1 Satz]   Betroffen: [Systeme/Mandanten]   Stand: [eingedämmt ja/nein]
Nächster Schritt: [wer, bis wann]
Keine Zugangsdaten oder Kundendaten in diesem Kanal teilen.
```

### Vorlage D: Statusmeldung (Website/Statusseite)

```
Wir untersuchen derzeit [eine Störung / einen Sicherheitsvorfall]. Aus Vorsicht haben wir [Maßnahme, z. B.
Anmeldungen vorübergehend eingeschränkt]. Sie müssen sich ggf. neu anmelden. Nächste Information bis [Zeit].
```

## 10. Wiederherstellung aus dem Backup

Kurzfassung (Details und Rollen: `docs/betrieb-runbook.md`, Abschnitt 3; Skripte `scripts/backup.sh`, `scripts/restore.sh`):

1. Ursache beheben **bevor** wiederhergestellt wird, sonst wird derselbe Zustand wieder angegriffen.
2. Frischen Host bzw. bereinigtes System aufsetzen, Secrets neu erzeugen/rotiert einspielen
   (`scripts/init-secrets.sh`), **Key-Datei `data_encryption_keys` mit allen alten Keys**, sonst sind
   Daten und Audit-Log nicht lesbar.
3. Restore der Datenbank: `BACKUP_AGE_IDENTITY_FILE=<privater Schlüssel> ./scripts/restore.sh backups/db_<TS>.sql.gz.age`
   (überschreibt die Datenbank, fragt mit „JA“). Upload-Volume gemäß Kommentar am Ende von `restore.sh`.
4. `alembic upgrade head`, Laufzeitrolle prüfen (`runtime_rolle.sql`), Smoke-Test, Datenlücke feststellen: Alles
   zwischen Backup-Zeitpunkt und Vorfall ist verloren. Betroffene Kunden darüber informieren.
5. Nach Wiederherstellung Passwörter/Sitzungen der betroffenen Konten zurücksetzen lassen.
6. Wiederherstellungsdauer und Datenstand ins Vorfallsprotokoll eintragen.

Ehrliche Grenze: Der Restore wurde im Rahmen dieses Dokuments **nicht** ausgeführt. Der reale
Restore-Test ist Release-Blocker 1 und liegt beim Betreiber.

## 11. Nach dem Vorfall

- Lessons Learned innerhalb von 14 Tagen: Ursache, Erkennungsdauer, was gefehlt hat (z. B. Alarm,
  IP-Logging, Rate-Limit pro IP), Maßnahmenliste mit Verantwortlichen und Terminen.
- Dokumentation (Art. 33 Abs. 5), TOMs (`docs/dsgvo-toms-entwurf.md`) und dieses Dokument anpassen.
- Übung: mindestens einmal jährlich einen Vorfall durchspielen (Tabletop), dabei die Rotation einmal auf
  Staging ausführen.

## 12. Offene Punkte (ehrlich)

- Keine Zugriffsprotokolle (Lesezugriffe) und keine IP-Adressen im Audit-Log: Abflüsse über gültige
  Sitzungen sind schwer nachzuvollziehen.
- Kein Rate-Limit pro IP im Code, nur Konto-Sperre nach Fehlversuchen.
- Kein Rotationsskript für `email_lookup_secret` und `blind_index_secret`.
- Passwort-Reset per E-Mail und MFA-Wiederherstellungscodes sind im Code vorhanden (Migration 0038). Offen bleibt der
  Support-Prozess für Konten, die weder Passwort/Postfach noch Gerät und Wiederherstellungscodes haben (manuelle
  Identitätsprüfung, danach MFA-Reset durch den Betreiber); er ist nicht definiert. Der Mailversand der Reset-Mails ist nur
  gegen Attrappen getestet.
- Monitoring/Alarmierung und Statusseite (7.5) sind noch nicht eingerichtet.
- Alle Rechts- und Fristenaussagen sind ungeprüft, siehe Hinweis am Anfang.
