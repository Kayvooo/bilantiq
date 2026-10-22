# Vollständige Sicherheitsabnahme einer Wiederherstellung

Status: verbindlicher Abnahmeplan, kein Nachweis eines bereits ausgeführten Produktiv-Restores.

## Ziel

Ein erfolgreich eingespielter SQL-Dump genügt nicht. Eine Wiederherstellung muss zeigen, dass Datenbank, Originaldateien,
Schlüsselversionen, Anwendungsstand und Berechtigungen zusammenpassen. Vor einer Betriebsfreigabe Verantwortlichen,
maximal akzeptierten Datenverlust (RPO) und Wiederanlaufdauer (RTO) festlegen.

## Testumgebung und Eingaben

- Isolierter Ersatzhost, ohne Zugänge/Netzverbindungen zum Produktionssystem. Kein Test gegen die produktive Datenbank.
- Backup-Paar von DB und Dateien mit Manifest, passender Anwendungsversion und gesichertem Migrationsstand.
- Backup-Entschlüsselungsidentität sowie alle für diesen Stand erforderlichen Anwendungsschlüssel getrennt bereitstellen.
- SMTP und KI während der Abnahme deaktivieren. Keine echten E-Mails oder externen Modellanfragen auslösen.
- Das Offsite-Ziel muss gegen Löschung/Überschreiben durch den Produktivhost geschützt sein; fehlendes `rsync --delete`
  allein gewährleistet diese Trennung nicht. Zugang und Aufbewahrungsregeln am Ziel prüfen.

## Ablauf und Nachweise

1. Manifest/Prüfsummen prüfen und `scripts/restore-test.sh` als Strukturtest ausführen. Dieses Skript prüft keine
   vollständige Anwendungskryptografie und keinen fachlichen Zugriff.
2. Auf dem Ersatzhost die **passende** Anwendungsversion und Secrets installieren. Dump und Dateiarchiv nach
   `docs/backup-restore.md`/`docs/rollback.md` einspielen; fehlende historische Keys nicht durch neue ersetzen.
3. Getrennte Migrations-/Laufzeitverbindung gemäß `docs/security-runtime.md` herstellen. Vor neuen Schema-Migrationen
   zuerst die Wiederherstellung des gesicherten Stands prüfen.
4. Anmeldung einschließlich MFA/Recovery mit dafür angelegtem Testkonto, aktueller Sitzung und Widerruf testen.
5. Ausgewählte verschlüsselte Stamm-/Kontakt-/Betragsfelder verschiedener Mandanten und Key-Versionen lesen. Ergebnis
   gegen den vorher dokumentierten Testbestand prüfen; Klartextdaten nicht in den Abnahmebericht aufnehmen.
6. Originalbeleg und Archivdateien entschlüsseln, Hash und fachliche Zuordnung prüfen. Rechnung und PDF-Ausgabe prüfen.
7. Mandantenfremde Zugriffe sowie verändernde Audit-Zugriffe müssen scheitern. Admin-Secret darf im API-Container fehlen.
8. Referenzintegrität zwischen Datenbank und Dateibestand prüfen. Ein zeitlich getrennter DB-Dump und Dateitar bilden
   ohne weitere Abstimmung keinen garantierten gemeinsamen Sicherungszeitpunkt. Für kleine Instanzen Schreibpause;
   andernfalls abgestimmte Snapshots oder versionierten Dateibestand/Backup-Wasserstand entwickeln.
9. Dauer und Datenstand gegen RTO/RPO bewerten. Fehlende Dateien, Keys und ungeklärte Abweichungen sind Abnahmefehler.
10. Alarm-/Backup-Zustellung und kontrollierten Wiederanlauf prüfen. Regelmäßig sowie nach relevanten Migrationen und
    Schlüsseländerungen wiederholen.

## Abnahmeprotokoll

| Feld | Eintrag |
| --- | --- |
| Datum, Verantwortlicher, Ersatzhost | ausfüllen |
| Anwendung-Commit, Alembic-Stand | ausfüllen |
| Backup-Zeitpunkt/Manifest | ausfüllen |
| benötigte Key-IDs vorhanden | ja/nein; keine Schlüsselwerte |
| Strukturtest | bestanden/fehlgeschlagen |
| Login/MFA/Widerruf | bestanden/fehlgeschlagen |
| Feld-/Dateientschlüsselung und Referenzen | bestanden/fehlgeschlagen |
| Mandantentrennung und Audit-Schutz | bestanden/fehlgeschlagen |
| gemessener Datenverlust/Wiederanlauf | ausfüllen, mit Ziel vergleichen |
| offene Abweichungen und Entscheidung | ausfüllen |

Eine nur lesende automatisierte Anwendungsprüfung ist Teil des Claude-Arbeitspakets F7. Bis sie vorliegt, diese Punkte
manuell und mit belegtem Testbestand prüfen. Dieser Plan erstellt keine Sicherungen und ändert keine Produktivsysteme.
