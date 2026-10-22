# Datenexport und Datenübernahme

Deine Daten mitnehmen oder aus einem anderen Programm holen.

## Gesamtexport (Auskunft und Datenübertragbarkeit)

1. Öffne in der Anwendung Mehr → Sicherheit & Datenschutz.
2. Wähle im Abschnitt „Datenschutz“ die Schaltfläche „Meine Daten exportieren“.
3. Du erhältst eine JSON-Datei mit dem Namen bilantiq-datenexport-JJJJ-MM-TT.json.

Den Export kann nur der Inhaber (Owner) des Unternehmens abrufen. Er enthält die gespeicherten Daten des gesamten Unternehmens, auch Mitglieder und Kontakte. Verschlüsselt gespeicherte Angaben wie E-Mail-Adressen sind darin lesbar.

## Was im Gesamtexport nicht enthalten ist

- Passwort-Hashes, MFA-Secrets und interne Prüfwerte
- Hochgeladene Dateien (Belege, Logo, Briefpapier): sie sind nur über ihre Referenz genannt, nicht als Dateien enthalten

## Weitere Exporte

- Kontakte und Produkte als CSV oder Excel über das Menü „Exportieren“ in der jeweiligen Liste (Inhaber)
- DATEV-Buchungsstapel als CSV (ab Pro) unter Mehr → Einnahmen-Überschuss-Rechnung
- Lohnvorbereitung als CSV-Arbeitsdatei (Business)
- Rechnungen, Angebote und Mahnungen als PDF

## Daten aus einem anderen Programm übernehmen

Unter Mehr → Datenumzug kannst du Kontakte, Produkte und Rechnungen aus Excel, CSV oder einem anderen Programm übernehmen. Ein Probelauf zeigt vorab, was passieren würde, und ein Import lässt sich rückgängig machen.

## Konto löschen

Beim Löschen werden deine Stammdaten anonymisiert. Gesetzlich aufzubewahrende Buchungsdaten bleiben entsprechend der Aufbewahrungslogik erhalten. Exportiere deine Daten vorher.

## Gut zu wissen

- Die Spaltenvorschläge beim Datenumzug sind bisher nur mit selbst erstellten Dateien getestet, nicht mit echten Exporten anderer Anbieter. Prüfe das Ergebnis im Probelauf.
- Der DATEV-Export ist nicht gegen ein echtes DATEV-System getestet, und die verwendeten SKR03-Konten sind nicht von einer Steuerberatung geprüft. Probiere ihn vor dem ersten Einsatz mit deiner Steuerberatung aus.
