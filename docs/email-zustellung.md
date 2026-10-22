# E-Mail-Zustellung

Stand: 14. Oktober 2026. und Phase 2 (SMTP-Secrets).

Diese Anleitung nutzt als Platzhalter die Domain `<deine-domain>` (in Beispielen `example.com`) und `<smtp-anbieter>`.
Konkrete Werte (SPF-Include, DKIM-Selektor, Schlüssel) liefert der gewählte SMTP-Anbieter in seiner Oberfläche; sie stehen
hier absichtlich nicht.

## Wie Bilantiq versendet

- `app/core/mailer.py`, stdlib `smtplib`: Verbindung zu `SMTP_HOST:SMTP_PORT` (Standard 587), dann STARTTLS, dann Login, dann Versand.
  Port 465 (implizites TLS) wird nicht unterstützt.
- **SMTP ist optional.** Ohne `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` und Absenderadresse startet die App trotzdem; Versand,
  „Passwort vergessen“ und die E-Mail-Bestätigung bei Adressänderung antworten dann mit HTTP 503 und einer klaren Meldung
  (siehe `docs/self-hosting.md`, Abschnitt 7).
- Absenderadresse ist immer `SMTP_ABSENDER`; ohne Angabe wird `SMTP_USER` verwendet, falls es eine E-Mail-Adresse ist, sonst
  ist E-Mail abgeschaltet. Es gibt keinen voreingestellten Absender mehr (früher `noreply@bilantiq.de`: eine fremde Domain als
  Absender wäre Spoofing). Der **Anzeigename** ist die Firma des Mandanten
  (bei Sicherheitsmails "Bilantiq"). Versendet werden Rechnungen, Angebote, Mahnungen (je mit PDF) und Sicherheitscodes (Text).
- Reine Textmails, ein Empfänger pro Nachricht, synchron im Request, keine Warteschlange, keine Wiederholung, keine Bounce-Auswertung.

## Durchsicht von `app/core/mailer.py`: Befunde und Änderungen

| Befund (alter Stand) | Bewertung | Änderung / Stand |
| --- | --- | --- |
| `starttls()` ohne Kontext: Pythons Standardkontext prüft **weder Zertifikat noch Hostnamen** | Hoch: ein Angreifer im Netzwerkpfad könnte SMTP-Zugangsdaten und Rechnungs-PDFs mitlesen | `ssl.create_default_context()` (Kette und Hostname werden geprüft). Test mit lokalem SMTP-Server und selbstsigniertem Zertifikat: Versand scheitert, kein Login. Beim alten Code schlug derselbe Test fehl |
| TLS-Pflicht | STARTTLS war Pflicht (kein Klartext-Fallback), da `starttls()` ohne Server-Unterstützung eine Ausnahme wirft | Beibehalten, jetzt per Test belegt: Login und Versand finden dann nie statt |
| Header-Injection über Betreff/Absendername/Empfänger | Der Python-E-Mail-Serializer wies Zeilenumbrüche bereits mit `HeaderParseError` ab (erst beim Serialisieren, also als Ausnahme mitten im Versand) | Betreff, Name und Dateiname werden bereinigt (Zeilenumbrüche werden zu Leerzeichen), Adressen streng geprüft (`ValueError` **vor** dem Verbinden). Tests mit `\r\nBcc:` in allen Feldern |
| Absender `f"{name} <{adresse}>"` als ein Header | Mit Umlauten im Firmennamen (z. B. "Müller & Söhne GmbH") wurde der **gesamte** Header, auch die Adresse, als Encoded-Word kodiert: Mailclients und Spamfilter sehen keinen lesbaren Absender | `email.utils.formataddr`: nur der Name wird kodiert. Test prüft Roundtrip |
| Kein `Date`, kein `Message-ID` | Fehlen beides, bewerten Spamfilter schlechter (`smtplib` ergänzt sie nicht) | Beides wird gesetzt (Message-ID mit Domain von `SMTP_ABSENDER`) |
| Kein Timeout | Ein hängender SMTP-Server blockiert den Request unbegrenzt | 30 s |
| `quit()` im `finally` konnte den ursprünglichen Fehler verdecken | | Fehler beim `quit()` werden abgefangen, Verbindung geschlossen |
| Kein `Reply-To` | Antworten des Kunden gehen an `noreply@...` | Verdrahtet (Release-Härtung): Rechnung, Angebot und Mahnung setzen `Reply-To` auf die **Anmelde-Adresse des versendenden Nutzers** (`app/core/mailversand.py`). Ein eigenes Kontaktadress-Feld am Mandanten gibt es nicht und würde eine Migration brauchen; die Anmelde-Adresse wird dadurch für Empfänger sichtbar. Abschaltbar mit `EMAIL_REPLY_TO_NUTZER=false`. Ungültige Adressen werden verworfen (kein Reply-To statt Fehler) |

Offene Punkte, die ich nicht geändert habe:

- **Missbrauchsschutz (umgesetzt, mit Grenzen):** `POST /invoices/{id}/versenden`, `/angebote/{id}/per-email-senden` und
  `/mahnungen/{id}/versenden` sind je Mandant begrenzt: Standard 30 E-Mails pro Stunde und 100 pro 24 Stunden
  (`EMAIL_LIMIT_PRO_STUNDE`, `EMAIL_LIMIT_PRO_TAG`, `0` = aus; Antwort `429` mit `Retry-After`). Gezählt wird aus dem Audit-Log
  (erfolgreiche Versandaktionen), also neustartfest, ohne neue Tabelle. Grenzen: Fehlgeschlagene SMTP-Versuche zählen nicht; parallele
  Anfragen können das Limit um wenige Mails überschreiten; das Limit gilt je Mandant, wer viele Konten registriert (Registrierung ist
  nur je IP begrenzt), hat je Konto ein Kontingent; Empfänger und Text bleiben frei wählbar (Rechnungen/Angebote/Mahnungen gehen an die
  hinterlegte Kontakt-Adresse, bei eigenem Text ist der Inhalt frei). Die Default-Werte sind eine Annahme, keine Messung.
- **EHLO-Name:** `smtplib` meldet den Hostnamen des Containers (eine zufällige ID). Authentifizierte Relays stört das meist nicht; einzelne Anbieter bewerten es. Falls ein Anbieter es bemängelt, `local_hostname` setzen.
- Keine Zustellstatus-/Bounce-Auswertung: Ein harter Bounce (falsche Adresse) merkt Bilantiq nicht. `versendet_am` heißt "SMTP hat die Nachricht angenommen", nicht "ist angekommen".
- Zertifikatsprüfung bedeutet: Der SMTP-Anbieter braucht ein von einer öffentlichen CA signiertes Zertifikat und `SMTP_HOST` muss dessen Namen tragen. Ein lokaler Test-SMTP mit selbstsigniertem Zertifikat (z. B. Mailpit/MailHog im Standard) funktioniert **nicht** mehr. Für Staging einen Sandbox-Dienst mit gültigem Zertifikat (z. B. Mailtrap) verwenden.

## Domain einrichten: SPF, DKIM, DMARC

Voraussetzung: Ein **SMTP-Anbieter mit eigener Domain-Authentifizierung** (transaktionaler Relay oder Postfachanbieter mit SMTP-Zugang). Kein eigener Mailserver auf einer Server-IP: Dort kommen Reverse-DNS, IP-Reputation und Warm-up dazu, die für ein kleines Produkt unnötiges Risiko sind.

Empfehlung: Rechnungen mit der **Hauptdomain** oder einer dedizierten Subdomain (z. B. `mail.<deine-domain>`) als Absender senden. Eine Subdomain trennt den Ruf des Rechnungsversands von normaler Post. Dann `SMTP_ABSENDER=rechnung@mail.<deine-domain>` setzen.

Alle Einträge setzt du im DNS der Domain; die Werte kommen vom Anbieter.

### 1. SPF

Ein TXT-Eintrag auf dem Absender-Host, **nur einer** je Name:

```
<absender-host>.   TXT   "v=spf1 include:<spf-include-des-smtp-anbieters> -all"
```

- Beim Einführen zuerst `~all` (Softfail) und nach erfolgreichen Tests `-all`.
- Nutzt die Domain bereits Mail (z. B. Postfach für Menschen), die vorhandenen `include:` im selben Eintrag ergänzen. Höchstens 10 DNS-Abfragen (Includes) insgesamt, sonst ist SPF ungültig.
- Prüfen: `dig +short TXT <absender-host>`.

### 2. DKIM

Der Anbieter nennt einen Selektor und je nach Anbieter ein CNAME- oder TXT-Paar:

```
<selektor>._domainkey.<absender-host>.   CNAME   <wert-vom-anbieter>.
```

- 2048-Bit-Schlüssel wählen, falls der Anbieter das anbietet.
- **Wichtig für DMARC:** DKIM muss mit der **eigenen Domain** (`d=<deine-domain>`) signieren, nicht mit der Domain des Anbieters, sonst besteht die DMARC-Ausrichtung nicht.
- Prüfen: `dig +short CNAME <selektor>._domainkey.<absender-host>` und im Anbieter-Dashboard "Domain verifiziert".

### 3. DMARC

TXT-Eintrag auf `_dmarc.<deine-domain>`; schrittweise verschärfen:

```
Woche 0-4:   _dmarc.<deine-domain>.  TXT  "v=DMARC1; p=none; rua=mailto:dmarc-berichte@<deine-domain>; fo=1"
danach:      ...                          "v=DMARC1; p=quarantine; pct=25; rua=mailto:dmarc-berichte@<deine-domain>"
dann:        ...                          "v=DMARC1; p=reject; rua=mailto:dmarc-berichte@<deine-domain>"
```

- Das Postfach für die Berichte muss existieren; die XML-Berichte liest man am bequemsten mit einem Berichts-Auswertungsdienst (Entscheidung des Betreibers; Berichte enthalten Absender-IP-Adressen).
- Vor jedem Verschärfen mindestens 2 Wochen Berichte lesen: Kommen alle legitimen Quellen (Rechnungsversand, Website-Formulare, Postfächer) durch?
- Prüfen: `dig +short TXT _dmarc.<deine-domain>`.

### 4. Weitere Maßnahmen (optional)

- MTA-STS und TLS-RPT für eingehende Post sind für den reinen Versand nicht nötig.
- Postfach `abuse@` und `postmaster@` der Domain einrichten (Anbieter und Empfänger-Provider erwarten sie).
- Die Impressums-/Support-Adresse im Mailfuß sollte erreichbar sein, es sind sonst unzustellbare Antworten (`noreply`) zu erwarten.

## Testplan GMX / Gmail / Outlook

Durchzuführen auf **Staging** mit der echten Absenderdomain (oder einer Test-Subdomain) und dem echten SMTP-Anbieter, aber ausschließlich an eigene Testpostfächer. Voraussetzung: SPF/DKIM/DMARC sind gesetzt und im Anbieter verifiziert. Ergebnis jeweils eintragen.

Vorbereitung: je ein Testpostfach bei GMX, Gmail und Outlook.com (oder Microsoft 365); in Staging ein Mandant mit Wegwerfdaten, drei Kontakte mit je einer dieser Adressen, je eine finalisierte Rechnung, ein Angebot, eine Mahnung. Firmenname mit Umlaut und Sonderzeichen ("Müller & Söhne GmbH").

| # | Prüfung | GMX | Gmail | Outlook |
| --- | --- | --- | --- | --- |
| 1 | Rechnung per "Per E-Mail senden": kommt im Posteingang an (nicht Spam)? | | | |
| 2 | Angebot per E-Mail: Posteingang? | | | |
| 3 | Mahnung per E-Mail: Posteingang? | | | |
| 4 | Sicherheitsmail (E-Mail-Änderungscode): Posteingang? | | | |
| 5 | Kopfzeilen zeigen `spf=pass`, `dkim=pass`, `dmarc=pass` (Gmail: "Original anzeigen"; Outlook: Internet-Header; GMX: "Quelltext") | | | |
| 6 | Absenderanzeige korrekt ("Müller & Söhne GmbH", nicht kodiert/verstümmelt) und Adresse lesbar | | | |
| 7 | Betreff und Text mit Umlauten korrekt | | | |
| 8 | PDF-Anhang öffnet, Dateiname stimmt (`Rechnung_<Nr>.pdf`) | | | |
| 9 | Antwort auf die Mail: geht dorthin, wo sie hingehen soll? (heute `noreply`, siehe offene Punkte) | | | |
| 10 | Darstellung am Handy (Textumbruch, Anhang) | | | |
| 11 | Zeit zwischen Klick und Eingang (Sekunden) | | | |

Zusätzlich:

- **Spam-Bewertung:** eine Testmail an die von einem Spamtest-Dienst (z. B. mail-tester.com) genannte Adresse senden; Ergebnis und Hinweise notieren. Das ist ein externer Dienst, kein Teil von Bilantiq.
- **Reputation:** Google Postmaster Tools und Microsoft SNDS für die Absenderdomain bzw. -IP anlegen (aussagekräftig erst bei regelmäßigem Volumen).
- **Fehlerfälle:** falsches SMTP-Passwort in Staging: die Oberfläche muss einen Fehler zeigen und `versendet_am` darf nicht gesetzt werden; Empfänger mit Tippfehler-Domain: Bilantiq meldet Erfolg (SMTP nimmt an), der Bounce landet beim Absender-Postfach, nicht in Bilantiq.
- **Große PDFs:** Rechnung mit vielen Positionen und Briefpapier senden und die Anhangsgröße notieren; Anbieterlimits (Empfänger- und Absenderseite) prüfen.
- **Header-Auswertung per Kommandozeile:** gespeicherte Rohmail (`.eml`) mit `grep -iE '^(authentication-results|received-spf|dkim-signature|from|reply-to|message-id|date):'` ansehen.

## Eintragungen für den Betreiber

Secrets: `smtp_password` im Secrets-Verzeichnis (siehe `scripts/init-secrets.sh`), `SMTP_HOST`, `SMTP_USER`, `SMTP_PORT`, `SMTP_ABSENDER` in `.env.prod`. Produktions-SMTP nie in Staging verwenden (`scripts/check-staging-env.sh` warnt bei gleichem `SMTP_HOST`).

## Was geprüft wurde und was nicht

Geprüft (automatisierte Tests in `backend/tests/test_mailer.py`, SQLite/Python, keine Netzwerkziele außer `127.0.0.1`): TLS-Reihenfolge, Zertifikatsprüfung gegen einen echten lokalen STARTTLS-Server mit selbstsigniertem Zertifikat, Ablehnung von Servern ohne STARTTLS, Injection-Fälle, Umlaute im Absender, Date/Message-ID, Timeout.
**Nicht geprüft:** Versand über einen echten SMTP-Anbieter, SPF/DKIM/DMARC einer echten Domain, Zustellung bei GMX/Gmail/Outlook, Spam-Bewertung. Der Testplan oben ist dafür da und muss vom Betreiber mit echten Zugangsdaten ausgeführt werden.
