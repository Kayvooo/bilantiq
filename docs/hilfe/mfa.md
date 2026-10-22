# Zwei-Faktor-Anmeldung (MFA)

Einrichten, neu einrichten und deaktivieren.

## Worum es geht

Mit Zwei-Faktor-Anmeldung braucht jede Anmeldung zusätzlich einen 6-stelligen Code aus einer Authenticator-App (TOTP). Das schützt dein Konto auch dann, wenn jemand dein Passwort kennt.

Sie ist optional, wird aber dringend empfohlen. Solange sie nicht eingerichtet ist, erinnert dich die Anwendung nach jeder Anmeldung einmal am Dashboard daran.

## Einrichten

1. Öffne in der Anwendung Mehr → Sicherheit & Datenschutz und im Abschnitt „Zwei-Faktor-Anmeldung“ die Schaltfläche „Zwei-Faktor-Anmeldung einrichten“.
2. Es erscheint ein Secret. Trage es manuell in deine Authenticator-App ein (zum Beispiel Aegis oder Google Authenticator) oder nutze den Link „In Authenticator-App öffnen“ auf dem Gerät, auf dem die App installiert ist. Ein QR-Code wird derzeit nicht angezeigt.
3. Gib den aktuellen 6-stelligen Code der App ein und bestätige. Danach meldest du dich einmal neu an.

## Anmelden mit Zwei-Faktor-Anmeldung

Nach Passwort und Code kannst du „Dieses Gerät 30 Tage merken“ wählen. Das solltest du nur auf Geräten tun, die nur du benutzt.

## Neu einrichten (zum Beispiel neues Handy)

Im selben Abschnitt wählst du „MFA neu einrichten“. Dafür brauchst du dein aktuelles Passwort und einen aktuellen Code. Die bisherige Zwei-Faktor-Anmeldung bleibt aktiv, bis du den Code der neuen Einrichtung bestätigt hast.

## Deaktivieren

1. Öffne Mehr → Sicherheit & Datenschutz → Zwei-Faktor-Anmeldung.
2. Gib dein aktuelles Passwort und einen aktuellen 6-stelligen Code ein und wähle „MFA deaktivieren“.
3. Alle Sitzungen werden beendet; du meldest dich danach neu an, ohne zweiten Faktor.

## Gut zu wissen

- Bei der Einrichtung zeigt Bilantiq dir Wiederherstellungscodes. Jeder Code funktioniert einmal, falls dein Handy oder deine Authenticator-App nicht verfügbar ist. Bewahre sie sicher und getrennt vom Handy auf.
- Wenn du Gerät und Wiederherstellungscodes verlierst, kannst du dein Konto nicht selbst zurücksetzen. Wende dich an die Person, die deine Bilantiq-Instanz betreibt: Sie kann den Zugang auf dem Server wiederherstellen (siehe `docs/self-hosting.md`, Abschnitt Konto wiederherstellen).
- Authenticator-Codes gehören nie in eine Nachricht an andere.
