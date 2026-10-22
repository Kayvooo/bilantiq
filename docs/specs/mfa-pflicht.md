# MFA-Pflicht und erneute Bestätigung sensibler Aktionen (F3)

Stand: 22. Oktober 2026. Grundlage: Sicherheits-Arbeitsauftrag F3, Review-Basis `c63413a`.

## Problem

`auth/routes.py::_ohne_mfa_anmelden` stellte jedem Konto ohne MFA eine **volle** Sitzung aus. Wer das Passwort eines Owners kennt
(Phishing, Wiederverwendung, Passwortmanager-Leck), kam ohne zweiten Faktor an alle Finanz- und Personaldaten, an die IBAN und
an den Gesamtexport. Außerdem: Auch mit aktivem MFA reichte ein einmal gestohlenes Token (bis 30 Tage bei „Gerät merken“), um
die IBAN umzustellen oder Zugänge anzulegen.

## Ziel

1. Ein Owner arbeitet nur mit eingerichtetem zweiten Faktor. Bis dahin sind ausschließlich die Einrichtungsrouten erreichbar.
2. Für andere Rollen gibt es eine serverseitige, dokumentierte Richtlinie.
3. Wenige besonders sensible Aktionen verlangen eine **frische** Bestätigung mit dem zweiten Faktor.
4. Recovery (Geräteverlust, Notfall) öffnet keine Hintertür, und ein einziger Owner steht nicht ohne Weg zurück da.

Nicht Ziel: ein neues Rollenmodell (das ist F2), neue Faktoren (WebAuthn/Passkeys), E-Mail-basierte MFA-Umgehung.

## Richtlinie `MFA_PFLICHT`

| Wert | Wirkung |
| --- | --- |
| `owner` (Standard) | Mandantenrolle `owner` braucht MFA. `mitglied` darf MFA nutzen, muss aber nicht. |
| `alle` | Jede Rolle braucht MFA. |
| `aus` | Keine Pflicht und **keine Bestätigung** sensibler Aktionen. **Nur mit `APP_ENV=development` zulässig**, sonst startet die App nicht. Gedacht für Tests und lokales Ausprobieren. |

Die Rolle wird bei jedem Aufruf aus der Mitgliedschaft gelesen, nicht aus dem Token. Ein Rollenwechsel oder eine geänderte
Richtlinie wirkt deshalb sofort auch auf bestehende Sitzungen.

## Verhalten

### Anmeldung und Registrierung

- Konto ohne MFA, Rolle mit Pflicht: `POST /auth/login` und `POST /auth/register` antworten mit
  `status: "mfa_einrichtung_erforderlich"` und **nur** `pre_auth_token` (15 Minuten). Kein `access_token`.
- Das `pre_mfa`-Token öffnet ausschließlich `POST /auth/mfa/setup` und `POST /auth/mfa/verify` (unverändert). Erst
  `mfa_verify` stellt die volle Sitzung aus und liefert bei der ersten Aktivierung die zehn Wiederherstellungscodes.
- Konto ohne MFA, Rolle ohne Pflicht: wie bisher `mfa_optional` mit voller Sitzung und Hinweis im Dashboard.

### Bestandsupgrade

- Bereits ausgestellte volle Sitzungen eines Owners ohne MFA werden **nicht** einzeln widerrufen. Stattdessen prüft
  `require_full_auth` bei jedem Aufruf Richtlinie, Rolle und `users.mfa_enabled` und antwortet mit 401
  („Zwei-Faktor-Anmeldung muss eingerichtet werden. Bitte melde dich neu an.“). Das Frontend leitet bei 401 zur Anmeldung, und
  dort beginnt der Einrichtungsweg. Es ist keine Datenmigration nötig; es ändert sich kein Schema.
- Folge für Bestandsinstanzen: Der erste Aufruf nach dem Update wirft jeden Owner ohne MFA einmal aus der Sitzung. Das ist
  beabsichtigt und gehört in die Update-Hinweise (CHANGELOG).

### MFA abschalten

- `POST /security/mfa/deaktivieren` ist für Rollen mit Pflicht gesperrt (403). Neu einrichten (anderes Gerät) bleibt über
  `/security/mfa/neu-einrichten` mit Passwort und aktuellem Code möglich.

### Erneute Bestätigung („Step-up“)

Aktionsklassen:

| Klasse | Aktion |
| --- | --- |
| `iban_aendern` | `PATCH /auth/mandant`, sobald sich IBAN oder BIC tatsächlich ändern |
| `benutzer_verwalten` | `POST /auth/einladungen`, `POST /auth/mitglieder`, `POST /auth/mitglieder/{id}/entfernen` |
| `gesamtexport` | `GET /auth/datenexport` |

Ablauf:

1. Aufruf ohne gültige Bestätigung: **HTTP 428** mit `detail` „Bitte bestätige die Aktion mit einem aktuellen Code …“.
2. `POST /auth/bestaetigung` mit `{aktion, code}` (volle Sitzung nötig). `code` ist ein aktueller TOTP-Code (6 Ziffern) oder
   ein Wiederherstellungscode. Prüfung mit Fehlversuchszähler, Sperre und Replay-Schutz wie bei der Anmeldung. Antwort:
   `bestaetigung_token` und `gueltig_bis`.
3. Wiederholung des Aufrufs mit Header `X-Bestaetigung: <token>`.

Das Token ist ein signiertes JWT (`scope=bestaetigung`) mit Konto, Sitzung (`sid`), Mandant, `security_version`, Aktionsklasse
und **5 Minuten** Gültigkeit. Es gilt nur für diese Sitzung, dieses Konto und diese Aktionsklasse. Passwort-/MFA-Änderung
(`security_version`) und Sitzungswiderruf entwerten es sofort. Es ist nicht an einen einzelnen Aufruf gebunden: Innerhalb der
fünf Minuten gilt es für beliebig viele Aufrufe derselben Klasse.

- Das Frontend hält das Token höchstens vier Minuten nur im Arbeitsspeicher (nie in `localStorage`), je Sitzung und Aktionsklasse, und fragt neu, sobald der Server 428 antwortet.
- „Gerät merken“ verlängert nur die Sitzung und ersetzt **keine** Bestätigung. Ein Token aus der Anmeldung zählt nie als frisch.
- Wegen des TOTP-Replay-Schutzes lässt sich der Code, der gerade zur Anmeldung diente, nicht noch einmal verwenden. Wer sich
  gerade angemeldet hat, wartet für die Bestätigung bis zu 30 Sekunden auf den nächsten Code.
- Bei `MFA_PFLICHT=aus` oder ohne MFA im Konto entfällt die Bestätigung (sonst wäre die Aktion nie ausführbar).

### Recovery

- Wiederherstellungscodes: wie bisher (10 Stück, einmalig angezeigt). Das Frontend zeigt sie bei der Pflicht-Einrichtung vor der
  Weiterleitung und verlangt die Bestätigung „gespeichert“.
- Passwort vergessen: ändert nur das Passwort, MFA bleibt aktiv (unverändert).
- Betreiber-Notfall (Gerät **und** Codes weg): `python -m scripts.konto_wiederherstellen --email … --mfa-zuruecksetzen` bleibt der
  einzige Weg. Er ist protokolliert (`konto_wiederhergestellt_betreiber`) und widerruft alle Sitzungen. **Die Richtlinie wird dadurch nicht
  umgangen:** Der Owner muss sich beim nächsten Login neu einrichten, ein Zugang ohne MFA entsteht nicht.
- Einziger Owner: Es gibt keinen automatischen Weg zurück (bewusst, siehe `docs/security-production.md`). Der Weg über den
  Betreiber ist dokumentiert; wer die Instanz selbst betreibt, ist dieser Betreiber.

## Nicht geändert

- TOTP-Replay-Schutz, Wiederherstellungscodes, Brute-Force-Zähler, serverseitiger Sitzungswiderruf, Argon2id.
- `DELETE /auth/me` verlangt weiterhin Passwort und Code.

## Annahmen, die ich getroffen habe

1. **Nur der Owner ist Pflicht**, Mitglieder nicht. Begründung: Ein Mitglied kann weniger (Lohn, IBAN, Zugänge, Gesamtexport
   sind Owner-only). Für Instanzen mit vielen Mitgliedern gibt es `MFA_PFLICHT=alle`. Ob das Standard werden soll, ist eine
   Produktentscheidung; die Feinaufteilung der Rechte folgt in F2.
2. **Der Onboarding-Scope ist das bestehende `pre_mfa`-Token**, kein neuer Token-Typ. Das hält die Angriffsfläche klein
   (zwei Routen), kostet keine Migration und lässt `require_full_auth` unverändert streng.
3. **Bestandsupgrade per Laufzeitprüfung statt Widerruf.** So bleibt kein alter Token übrig, ohne dass eine Migration Sitzungen
   anfassen muss.
4. **Step-up ohne Einmalbindung, 5 Minuten.** Einmalige Tokens würden bei Mehrfachaktionen (mehrere Zugänge anlegen)
   zehnmal einen Code verlangen. Das Fenster ist kurz, an Sitzung und Klasse gebunden.
5. **Bestätigung per Code, ohne Passwort.** Passwort plus Code verlangen bereits die Aktionen am MFA selbst. Für die hier
   genannten Klassen schützt der Code gegen ein gestohlenes Token; ein zusätzliches Passwort würde die Bedienung verschlechtern,
   ohne das Szenario „Token gestohlen, Gerät nicht“ weiter abzudecken.
6. **Der Betreiber-Reset schaltet MFA ab und erzwingt anschließend die Neueinrichtung.** Er wird nicht zu einem Zugang ohne MFA.

## Grenzen und verbleibende Risiken

- Wer Passwort **und** Authenticator-Gerät (oder die Codes) eines Owners hat, besteht jede Prüfung. MFA schützt nicht vor einem
  übernommenen Endgerät.
- DATEV-Export, Storno, Bankimport und andere Fachaktionen verlangen noch **keine** Bestätigung. Sie gehören in die
  Rechtematrix von F2.
- `MFA_PFLICHT=aus` ist für Entwicklung gedacht. In der Standard-Testkonfiguration ist es gesetzt; die Pflicht selbst ist in
  `backend/tests/test_mfa_pflicht.py` getestet.
- Ein Angreifer mit Zugriff auf den Server (Schlüssel, Datenbank) wird durch nichts hier aufgehalten.
- Der Einrichtungsweg ist nur gegen Attrappen getestet (TOTP mit `pyotp`), nicht mit echten Authenticator-Apps.
