# Lohnbuchhaltung – Phase 3, erster sicherer Baustein

Status: GEBAUT (Vorbereitungsbaustein) · Freigabe: „Durchführung“ / „Fortsetzen“.

## Produktziel

Bilantiq erhält eine mandantengetrennte Lohnvorbereitung: Beschäftigte mit
Personalnummer, Name, Eintritt/Austritt und vereinbartem Monatsbrutto verwalten;
für einen Abrechnungsmonat Entwürfe mit Grundbrutto, steuerpflichtigen Zuschlägen,
steuerfreien Erstattungen und sonstigen Abzügen anlegen; Monat als CSV-Arbeitsdatei
für die Steuerkanzlei exportieren.

Personennamen werden mit der bestehenden Fernet-Feldverschlüsselung gespeichert.
Jeder Datensatz trägt `mandant_id`, alle Abfragen filtern explizit nach dem Mandanten,
Postgres erhält zusätzlich RLS. Anlage und Deaktivierung werden im unveränderlichen
Audit-Log dokumentiert. Beschäftigte werden deaktiviert statt gelöscht, damit
Monatsentwürfe nachvollziehbar bleiben.

## Bewusste Grenze

Der erste Baustein berechnet ausschließlich mathematisch überprüfbare Summen:

`Gesamtbrutto = Grundbrutto + steuerpflichtige Zuschläge`

`Zwischensumme vor gesetzlichen Abgaben = Gesamtbrutto + steuerfreie Erstattungen − sonstige Abzüge`

Er berechnet ausdrücklich keine Lohnsteuer, Kirchensteuer, Solidaritätszuschlag,
Kranken-, Pflege-, Renten- oder Arbeitslosenversicherungsbeiträge und erzeugt keine
Lohnabrechnung, Beitragsnachweise, DEÜV-/ELStAM-/eAU-Meldung oder Lohnsteuerbescheinigung.
Entwürfe können deshalb weder „finalisiert“ noch als rechtsverbindliche Abrechnung
ausgegeben werden. UI, API und CSV benennen diese Grenze sichtbar.

## Warum diese Grenze notwendig ist

- Der BMF-Programmablaufplan ist die Grundlage für Lohnsteuer, Solidaritätszuschlag
  und Kirchenlohnsteuer-Bemessung. Das BMF weist darauf hin, dass sein Rechner keine
  Sozialabgaben berechnet; die externe Schnittstelle ist nur für Programmtests erlaubt.
  Quelle: https://www.bmf-steuerrechner.de/
- Für den elektronischen Datenaustausch mit Sozialversicherungsträgern dürfen laut
  ITSG ausschließlich systemgeprüfte Programme eingesetzt werden. Die Erstprüfung
  umfasst umfangreiche Testaufgaben und eine Pilotprüfung mit mindestens zwei
  Programmanwendern. Erst danach gibt es Zertifikat und jährlich gültige Prod-MOD-ID;
  ungültige Versionen werden abgewiesen.
  Quelle: https://www.itsg.de/produkte/systemuntersuchung/
- Krankenkassen-Zusatzbeiträge unterscheiden sich je Kasse; Jahreswerte und Grenzen
  ändern sich. Eine feste Pauschale wäre keine echte Abrechnung.
  Quelle: https://www.bundesgesundheitsministerium.de/beitraege

## API und Datenmodell

- `POST/GET /lohn/mitarbeitende`, `POST /lohn/mitarbeitende/{id}/deaktivieren`
- `POST/GET /lohn/monatsentwuerfe`
- `GET /lohn/monate/{jahr}/{monat}/export`
- `Mitarbeiter`: verschlüsselter Vor-/Nachname, Personalnummer, Beschäftigungszeitraum,
  vereinbartes Monatsbrutto, aktiv.
- `LohnMonatsentwurf`: Mitarbeiter, Jahr/Monat, vier Eingabebeträge und gespeicherte
  Summen. Eindeutig je Mitarbeiter und Monat. Status immer `vorbereitung`.

## Nicht erfüllt für eine echte Lohnabrechnung

Vor Produktivfreigabe fehlen mindestens: fachlich vollständiges Stammdatenmodell,
versionsgebundene Umsetzung und amtliche Testvektoren des BMF-PAP, kassenindividuelle
SV-Daten, Sonderfälle und Rückrechnungen, Entgeltbescheinigungsverordnung, ELSTER/ERiC,
ITSG-Systemprüfung samt zwei Pilotanwendern, Datenschutz-Folgenabschätzung und
fachliche Abnahme durch Lohnsteuer-/Sozialversicherungsexperten.

## Abnahme

Sieben API-Tests prüfen Summen und Dezimalvalidierung, Eindeutigkeit je Monat,
Zeitraumgrenzen, Verschlüsselung, Mandantentrennung, Deaktivierung und
CSV-Kennzeichnung. Gesamtergebnis: 96 pytest-Tests grün; Alembic-Migration 0009
bis Head erfolgreich; Frontend-Typecheck, oxlint und Vite-Build grün. Live über
uvicorn wurden Registrierung/MFA, Mitarbeiteranlage, Monatsentwurf und CSV
erfolgreich verarbeitet. Der Server bestätigte, dass verbindlicher Abschluss
deaktiviert ist.
