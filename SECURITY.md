# Sicherheitsrichtlinie

Bilantiq ist ein Open-Source-Projekt zum Selbst-Hosten. Es gibt keinen gehosteten Dienst des Projekts; jede Person betreibt
ihre eigene Instanz (siehe [docs/self-hosting.md](docs/self-hosting.md)). Diese Datei beschreibt, wie Sicherheitslücken in
**der Software** gemeldet werden und was das Projekt dazu zusagt und nicht zusagt.

## Sicherheitslücke melden

Bitte melden Sie Schwachstellen **nicht** als öffentliches Issue, sondern vertraulich über GitHub:

1. Im Repository den Reiter **Security** öffnen.
2. **Report a vulnerability** wählen („Private vulnerability reporting“) und das Formular ausfüllen.

> **Platzhalter für den Projektinhaber:** Dieser Meldeweg funktioniert nur, wenn „Private vulnerability reporting“ in den
> Repository-Einstellungen (Settings → Code security) aktiviert ist. Das wurde hier nicht geprüft. Falls Sie stattdessen
> oder zusätzlich eine E-Mail-Adresse angeben möchten, tragen Sie sie hier ein: `[SECURITY-KONTAKT-EINTRAGEN]`.

Hilfreich in einer Meldung: betroffene Version bzw. Commit, Beschreibung und Auswirkung, Schritte zum Nachstellen (gern mit
einem minimalen Beispiel), und ob Sie die Lücke bereits an Dritte weitergegeben haben. Bitte senden Sie keine echten
Geschäfts- oder Personendaten und keine echten Schlüssel.

Wir bemühen uns, den Eingang zeitnah zu bestätigen und gemeinsam eine Lösung abzustimmen, bevor Details veröffentlicht
werden. Feste Antwort- oder Behebungsfristen werden nicht zugesagt, es handelt sich um ein Projekt ohne Vertrag und ohne
Dienstgütevereinbarung (SLA).

## Unterstützte Versionen

Sicherheitskorrekturen gibt es nur für den **aktuellen Stand des Hauptzweigs (`main`)** und das jeweils **neueste Release**.
Ältere Stände werden nicht gepflegt. Wer Bilantiq betreibt, ist selbst dafür zuständig, Updates einzuspielen
(`docs/self-hosting.md`, Abschnitt Updates).

## Geltungsbereich

Im Geltungsbereich sind Schwachstellen im Code dieses Repositories, z. B. Umgehung der Mandantentrennung oder der
Authentifizierung, Offenlegung oder Manipulation von Daten, Fehler in der Verschlüsselung oder der Dateiablage
(Path Traversal), Einschleusen von Code (XSS, Injection) oder unsichere Voreinstellungen.

Nicht im Geltungsbereich:

- Ihre eigene Instanz und ihr Betrieb: Fehlkonfiguration, schwache oder verlorene Schlüssel und Passwörter, ungepatchte
  Server oder Docker-Hosts, offen gelassene Ports, fehlende Backups, kompromittierte Zugänge des Betreibers.
- Software von Dritten (Betriebssystem, Docker, Postgres, Caddy, Abhängigkeiten): bitte bei den jeweiligen Projekten melden;
  ist eine Abhängigkeit in Bilantiq verwundbar eingebunden, ist ein Hinweis willkommen.
- Reine Ausnutzung von Funktionen, die dokumentiert so gedacht sind (z. B. das Betreiber-Skript
  `backend/scripts/konto_wiederherstellen.py`, das Serverzugang voraussetzt).
- Denial-of-Service durch bloße Last, Social Engineering, physischer Zugriff, automatisierte Scanner-Berichte ohne
  nachvollziehbare Auswirkung.
- Fachliche Fehler bei Steuer-, Buchhaltungs- oder Rechtsfragen (E-Rechnung, DATEV, UStVA usw.): bitte als normales Issue melden.

## Keine Garantien

Bilantiq wird ohne jede Gewähr bereitgestellt (siehe Lizenz). Das Projekt gibt keine Zusage, dass die Software frei von
Sicherheitslücken ist, dass Daten geschützt bleiben oder dass sie steuerlichen oder datenschutzrechtlichen Anforderungen
genügt. Die Sicherheitsmaßnahmen im Code (u. a. Verschlüsselung gespeicherter Daten, Mandantentrennung, Sitzungs- und
Passwortschutz) ersetzen keinen sorgfältigen Betrieb und keine eigene Prüfung. Ein externer Penetrationstest ist in diesem
Repository nicht dokumentiert.

## Hinweise für Betreiber

Sicherheitsrelevante Updates werden im [CHANGELOG](CHANGELOG.md) und in den Release-Hinweisen benannt. Betreiber sollten das
Repository beobachten („Watch → Custom → Security alerts“) und Updates zeitnah einspielen.
