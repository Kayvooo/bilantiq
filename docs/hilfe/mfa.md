# Zwei-Faktor-Anmeldung (MFA)

Einrichten, neu einrichten und deaktivieren.

## Worum es geht

Mit Zwei-Faktor-Anmeldung braucht jede Anmeldung zusätzlich einen 6-stelligen Code aus einer Authenticator-App (TOTP). Das schützt dein Konto auch dann, wenn jemand dein Passwort kennt.

Für den Inhaber (Rolle „Owner“) ist sie Pflicht: Ohne eingerichtete Zwei-Faktor-Anmeldung zeigt Bilantiq nach dem Login nur den Einrichtungsbildschirm. Für Mitglieder ist sie optional (außer der Betreiber hat sie für alle vorgeschrieben) und wird dringend empfohlen; solange sie nicht eingerichtet ist, erinnert dich die Anwendung nach jeder Anmeldung einmal am Dashboard daran.

## Einrichten

1. Öffne in der Anwendung Mehr → Sicherheit & Datenschutz und im Abschnitt „Zwei-Faktor-Anmeldung“ die Schaltfläche „Zwei-Faktor-Anmeldung einrichten“.
2. Es erscheint ein Secret. Trage es manuell in deine Authenticator-App ein (zum Beispiel Aegis oder Google Authenticator) oder nutze den Link „In Authenticator-App öffnen“ auf dem Gerät, auf dem die App installiert ist. Ein QR-Code wird derzeit nicht angezeigt.
3. Gib den aktuellen 6-stelligen Code der App ein und bestätige. Danach meldest du dich einmal neu an.

## Anmelden mit Zwei-Faktor-Anmeldung

Nach Passwort und Code kannst du „Dieses Gerät 30 Tage merken“ wählen. Das solltest du nur auf Geräten tun, die nur du benutzt.

## Neu einrichten (zum Beispiel neues Handy)

Im selben Abschnitt wählst du „MFA neu einrichten“. Dafür brauchst du dein aktuelles Passwort und einen aktuellen Code. Die bisherige Zwei-Faktor-Anmeldung bleibt aktiv, bis du den Code der neuen Einrichtung bestätigt hast.

## Aktuellen Code bei sensiblen Aktionen

Bevor du die IBAN änderst, Zugänge anlegst oder entfernst oder alle Daten exportierst, fragt Bilantiq nach einem aktuellen Code (oder einem Wiederherstellungscode). Die Bestätigung gilt 5 Minuten für diese Art von Aktion. „Dieses Gerät merken“ ersetzt sie nicht. Hast du dich gerade erst angemeldet, kann es bis zu 30 Sekunden dauern, bis die App einen neuen Code anzeigt, denn derselbe Code lässt sich nicht zweimal verwenden.

## Deaktivieren

Als Inhaber (oder wenn der Betreiber MFA für alle vorschreibt) kannst du die Zwei-Faktor-Anmeldung nicht abschalten, nur auf einem neuen Gerät neu einrichten. Für alle anderen:

1. Öffne Mehr → Sicherheit & Datenschutz → Zwei-Faktor-Anmeldung.
2. Gib dein aktuelles Passwort und einen aktuellen 6-stelligen Code ein und wähle „MFA deaktivieren“.
3. Alle Sitzungen werden beendet; du meldest dich danach neu an, ohne zweiten Faktor.

## Gut zu wissen

- Bei der Einrichtung zeigt Bilantiq dir Wiederherstellungscodes. Jeder Code funktioniert einmal, falls dein Handy oder deine Authenticator-App nicht verfügbar ist. Bewahre sie sicher und getrennt vom Handy auf.
- Wenn du Gerät und Wiederherstellungscodes verlierst, kannst du dein Konto nicht selbst zurücksetzen. Wende dich an die Person, die deine Bilantiq-Instanz betreibt: Sie kann den Zugang auf dem Server wiederherstellen (siehe `docs/self-hosting.md`, Abschnitt Konto wiederherstellen).
- Authenticator-Codes gehören nie in eine Nachricht an andere.
