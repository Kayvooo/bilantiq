# Browser-Abnahme Frontend

Stand: 2026-10-14, Branch `release/browser-abnahme`. Dieses Dokument sagt ehrlich, **was** im echten Browser geprüft wurde,
**was** dabei gefunden und behoben wurde und **was nicht** prüfbar war.

## Methode und Grenzen der Methode

- Browser: Google Chrome for Testing 151 (headless, Linux), gesteuert per DevTools-Protokoll aus Node. Messungen mit
  `mobile: false` und fester Breite (320, 390, 768, 1280), nicht mit Mobil-Emulation, weil dort der Layout-Viewport
  aufgeweitet wird und `scrollWidth <= innerWidth` wertlos ist. Überlauf wird gegen `documentElement.clientWidth` gemessen
  (nicht `innerWidth`, sonst fällt ein Überlauf unter der Scrollleiste durch).
- **Das Backend war komplett gemockt** (ein `window.fetch`-Mock, vor der App geladen, nichts ging an localhost:8000, kein
  Login in die echte App). Geprüft wurde also die Oberfläche gegen **plausible Beispielantworten**, nicht gegen das echte
  Backend. Antwortformen, die der Mock nicht kennt, können Fehler verdecken oder erzeugen. Zwei Befunde während der Arbeit
  (Anlagen- und Suche-Seite) waren reine Mock-Artefakte und sind **keine** App-Fehler.
- PDF-Inhalte (Rechnungsvorschau, Vorlagen) wurden **nicht** inhaltlich geprüft: Die Vorschau lud ein einfaches Mock-PDF in
  den iframe, es ging nur um Rahmen, Zoom und Layout drumherum.
- Screenshots liegen nur im Scratchpad, nicht im Repository. Harness-Dateien gab es nicht im Repo (Mock per
  `addScriptToEvaluateOnNewDocument`, eigene Vite-Konfiguration wurde nach der Arbeit gelöscht).

## Was geprüft wurde (Breite / Seite)

Alle Seiten unten wurden bei **320, 390, 768 und 1280** auf horizontalen Seitenüberlauf, Eingabefelder ohne zugänglichen
Namen und JS-Fehler durchlaufen (Sweep über 28 Seiten, beim Abschluss erneut bei 390): Dashboard, Erste Schritte, Rechnungen,
Belege, Angebote, Kontakte, Produkte, Datenumzug, Benutzer & Rechte, Sicherheit & Datenschutz, Buchhaltung,
Unternehmen, Mahnungen, Kassenbuch, UStVA, EÜR, Mein Steuerberater, Cashflow, SuSa, BWA, Lohnvorbereitung, Sonstige
Einnahmen, Wiederkehrend, Gutschriften, Anlagen, KI-Assistent, Auftragsbestätigung, Lieferscheine, Kontoauszug. Ergebnis nach
den Korrekturen unten: **kein Seitenüberlauf** auf den geprüften Seiten (Tabellen scrollen bewusst in ihrem eigenen Container).

Zusätzlich im Detail, mit Screenshot und Messung:

| Bereich | Breiten | Geprüft |
|---|---|---|
| MFA-Hinweis-Popup am Dashboard | 320, 390, 768, 1280 | Anzeige, Maße im Viewport, `role=dialog`/`aria-modal`/`aria-labelledby`, Startfokus, Tab/Shift+Tab-Falle, Escape, „Später", „Jetzt einrichten" springt zur Sicherheitsseite, erscheint nach Schließen/Reload/Zurückkehren **nicht** wieder (Flag in `sessionStorage`, wird bei jeder Anmeldung ohne MFA neu gesetzt) |
| Sicherheitsseite | 320, 390, 768, 1280 | MFA einrichten (Secret, falscher/richtiger Code, danach Abmeldung), MFA neu einrichten, MFA deaktivieren mit leeren Feldern / falschem / richtigem Passwort+Code, Fehlermeldung bei fehlgeschlagener Einrichtung, Label-Klick fokussiert Feld |
| Registrierung / Login | 320, 390, 768, 1280 | Registrierung per Tastatur ohne MFA (landet am Dashboard mit Popup), Login falsch / ohne MFA / mit MFA und Code-Abfrage (falscher und richtiger Code), Ladezustand (Button gesperrt), Offline-Fehlertext |
| Desktop-Sidebar | 1280 (und 768/390 als Gegenprobe: ausgeblendet, Bottom-Nav) | Tab-Reihenfolge, Gruppen per Enter auf-/zuklappen (`aria-expanded`), `aria-current`, Fokusring auf dunklem Grund |
| Rechnungs-Editor | 320, 390, 768, 1024, 1280, 1440 | Layout, Positionen, Live-Vorschau-Rahmen, Zoom 50/75/100 % (Buttons, Disabled-Zustände, Rahmenbreite), Design-Tab |
| Lagerbestand-Buchung | 390, 1280 | Formular öffnen, Felder/Labels, Buchen (Bestand 40 → 45), Fehlerfall „Bestand darf nicht unter 0 fallen" |
| „Per E-Mail senden" | 320–1280 | Rechnungen, Angebote, Mahnungen: aktiv/deaktiviert je Status und Kontakt-E-Mail, Erfolg („Versendet am"), Fehler (SMTP-Fehlermeldung) |
| Leere Zustände | 390, 1280 | Dashboard, Rechnungen, Belege, Angebote, Kontakte, Produkte, Kassenbuch, Sonstige Einnahmen, Mahnungen: jeweils mit erklärendem Text und nächstem Schritt |
| Fehler-/Ladezustände | 390 | Dashboard- und Rechnungs-500 (mit „Erneut versuchen"), Ladetexte, Start ohne Netz, `/auth/me` 401 und 500, Dashboard 401 |
| Befehlspalette (Strg+K) | 1280 | `role=dialog`, Combobox, Fokusfalle, Escape, Treffer |
| Barrierefreiheit | 1280, 390 | s. unten |

### Barrierefreiheit (Minimum)

- **Kontraste:** Aus `frontend/src/styles/tokens.css`/`brand.css` berechnet (WCAG 2.x): Text auf Fläche 15,9:1, gedämpfter Text
  6,5:1, weiß auf Primärgrün 12,1:1, Fehlertext auf Fehlerfläche 5,4:1, Warn/Info/Success auf ihren Flächen 5,98 bis 6,3:1, Eingabe-
  rahmen 3,6:1 (Mindestwert 3:1 für UI-Komponenten), Fokusring (Blau) auf Weiß 6,7:1. **Schwäche in den Tokens:** Der Fokusring
  `#245CA6` hat auf dem Primärgrün `#143D2B` nur 1,8:1; er wird dort aber nur dank des weißen Innenrings der Sidebar sichtbar
  (Screenshot geprüft), nicht durch die Token-Farbe allein. Zusätzlich ein Scan aller sichtbaren Textknoten auf 13 Seiten bei
  1280 und 390 (berechnete Farbe gegen effektiven Hintergrund, Deckkraft berücksichtigt; Scanner mit absichtlich schlechtem
  Text gegengetestet): **kein Verstoß** (Schwelle 4,5:1, große Schrift 3:1). Deaktivierte Elemente sind ausgenommen.
- **Tastatur:** Registrierung, Login, MFA-Challenge, Popup, Palette und Sidebar sind per Tastatur bedienbar. Sichtbarer Fokus
  (3-px-Ring) bei allen durchgetabbten Elementen vorhanden.
- **Formularlabels:** Sweep über die oben genannten Seiten; gefundene Felder ohne Namen sind behoben (s. u.).
- **Dialog-Rollen:** Popup und Palette haben `role=dialog`, `aria-modal`, Namen und eine Fokusfalle.

## Gefunden und behoben (je ein Commit)

| Commit | Befund | Behebung |
|---|---|---|
| `6ff6e2f` | MFA-Popup: Nach Klick auf den Hintergrund lag der Fokus auf `body`, **Escape schloss nicht**, Shift+Tab sprang in die verdeckte Seite. „Später" saß 16 px höher als „Jetzt einrichten". | Tastaturbehandlung am Dokument statt am Dialog; Buttons fluchten |
| `e761143` | Sicherheitsseite: 9 Eingabefelder mit `<label>` ohne `for` (kein zugänglicher Name, Label-Klick tat nichts). Fehlermeldung stand oben, lag bei Aktionen weiter unten **außerhalb des Sichtbereichs**. | Labels verknüpft, `autocomplete`-Hinweise; Fehler scrollt ins Bild (später zentral gelöst) |
| `cfe7804` | Login/Registrierung/MFA-Code: Felder wurden während der Anfrage `disabled`, dadurch **Fokusverlust auf `body`** nach Enter/Fehler. Registrierungshinweis „richtest sofort die Zwei-Faktor-Anmeldung ein" stimmte seit der optionalen MFA nicht mehr. | `readOnly` statt `disabled`; Text korrigiert |
| `5e653d0` | Rechnungs-Editor: Positionstabelle braucht 724 px, im Split neben der Vorschau (ab 1024 px) stehen 300–510 px zur Verfügung, auf dem Handy 299 px; Einzelpreis/USt nur durch Scrollen in einer kleinen Box erreichbar. Design-Seite: Beschreibungen der Vorlagenkarten liefen bei 320/390 px aus der Karte und erzeugten **Seitenüberlauf** (349 px bei 305 px Breite). Datei-Felder für Logo/Briefpapier ohne Namen. | Positionen werden bei schmalem Container zu beschrifteten Feldblöcken (Container Query); Karten brechen Wörter um, unter 360 px einspaltig; `aria-label`s |
| `a2c6bb4` | Fehlermeldungen (`role=alert`) erscheinen oben auf der Seite, auch wenn die Aktion weit unten ausgelöst wurde (Bestand buchen, E-Mail senden …). Aufgeklappte Formulare in Tabellenzeilen (Bestand buchen, Bearbeiten …) waren auf 390 px Teil der 600 px breiten, scrollenden Tabelle und halb abgeschnitten. | Zentraler Beobachter (`lib/alertSichtbar.ts`) scrollt neue Meldungen bei Bedarf ins Bild; Formular in Tabelle klebt im sichtbaren Ausschnitt (auf Desktop unverändert) |
| `6f166d1` | Angebots- und Wiederkehrend-Formular: je 4 Positionsfelder ohne Label. | `aria-label` pro Feld und Position |
| `7eee6ec` | **App-Start mit gespeichertem Token, aber ohne Netz oder bei 5xx von `/auth/me`: Token wurde gelöscht und die Registrierung gezeigt** (stilles Ausloggen, bei installierter App besonders ärgerlich). Dashboard zeigte Ladefehler ohne „Erneut versuchen". | Eigener Fehlerzustand mit „Erneut versuchen" und „Zur Anmeldung"; Token wird nur bei 401 verworfen; Dashboard mit `PageState` |
| `c66d8fe` | Desktop: Sidebar (visuell links) war im DOM nach dem Inhalt, Tab erreichte sie erst nach der gesamten Seite. | Sidebar im DOM vor `main` |
| `0a580d5` | Donut-Diagramme: Beträge ab vier Stellen waren breiter als das Loch und liefen in den Ring; oberstes Y-Achsenlabel des Balkendiagramms halb abgeschnitten. | Schriftgröße je nach Länge; oberer Rand im Diagramm |
| `31e8e61` | Ein Render-Fehler (z. B. unerwartete Antwortform) entfernte die ganze Oberfläche, übrig blieb eine **weiße Seite** (ohne Hinweis). Reproduziert mit absichtlich falscher Suche-Antwort. | `ErrorBoundary` um die App mit „Seite neu laden" |
| `d2012bc` | „Per E-Mail senden" ist ohne Kontakt-E-Mail deaktiviert, der Grund stand nur im `title` (Touch/Tastatur unsichtbar). Sidebar hob bei Aufträge > Angebote Gruppe **und** Unterpunkt hervor. | Sichtbarer Hinweistext in Rechnungen, Angeboten, Mahnungen; nur der Unterpunkt leuchtet |
| `451d825` | Jedes Öffnen/Schließen der Suchpalette löste `/auth/me` und `/berichte/dashboard` neu aus (neue Callback-Funktion als Effekt-Abhängigkeit). | Callback über Ref |

Prüfungen am Ende: `tsc -b` grün, `oxlint` Exit 0 (eine vorhandene Warnung in `QuoteForm.tsx`, nicht von dieser Arbeit), Produktions-
build erfolgreich (Hinweis zu Chunk-Größe > 500 kB wie zuvor), `node --test tests/auth-entry.test.mjs` 3/3.

## Folgearbeit (Branch `release/frontend-folgen`)

Gleiches Vorgehen wie oben (Chrome for Testing 151, headless, DevTools-Protokoll, **komplett gemocktes `window.fetch`**, Dev-Server,
keine Harness-Dateien im Repo). Die Mock-Antworten sind ausgedacht; geprüft wurde das Verhalten der Oberfläche, nicht das Backend.

| Thema | Änderung | Im Browser geprüft (gemockt) |
|---|---|---|
| Abmelden | Es gab **keinen** Abmelden-Knopf für die eigene Sitzung. Jetzt „Abmelden" unter Mehr (Handy) und im Sidebar-Fuß; ruft `POST /auth/logout`, Fehler dabei blockieren das lokale Abmelden nicht | Aufruf mit Bearer-Token; Logout bei Netzfehler und bei 500 meldet trotzdem lokal ab; Handy-Weg über Mehr |
| 429 | Zentrale fetch-Hülle (`lib/rateLimit.ts`): bei 429 „Zu viele Versuche. Bitte versuche es in X Minuten erneut." aus `Retry-After` (Sekunden oder Datum), ohne Header bleibt der Servertext | Login (mit/ohne Header), MFA-Code, Registrierung mit Einladungscode, E-Mail-Änderung, MFA deaktivieren, MFA neu einrichten |
| Rollen | Mitglieder: Lohn in Sidebar/„Mehr" ausgeblendet, direkter Aufruf zeigt Erklärung (kein `/lohn`-Request); Unternehmen, Mein Steuerberater und IBAN/BIC im Rechnungsdesign schreibgeschützt mit Hinweis, Design-Felder bleiben änderbar | Owner und Mitglied, 1280 und 390 px |
| Einladungscode | 12 Zeichen: `minLength`/`pattern`, Platzhalter, Hinweistext; Einfügen mit Leer-/Bindestrichen wird normalisiert (Eingabegrenze 24, weil `maxLength=12` ein eingefügtes `3F9A-1C7D-02BE` abschnitt, im Browser-Check gefunden) | Einfügen, gesendeter Wert |
| MFA-Einrichtung | Toter Schritt `mfa-enroll`/`MfaEnrollment.tsx` samt `mfaSetup`/`mfaVerify` entfernt (Text „Scanne den Code" war falsch: es gibt keinen QR-Code) | `tsc` belegt Nichtnutzung; Einrichtung über die Sicherheitsseite unverändert |
| Vorschau | Rechnungsvorlagen-Vorschau als `POST` mit JSON-Body statt `GET` mit Query (IBAN/BIC/Fußzeile nicht mehr in der URL) | Request ist POST ohne Query, iframe zeigt `blob:`-URL. **Läuft erst gegen das echte Backend, wenn der Backend-Branch den Endpunkt umstellt.** |
| Strg+K | Öffnet keine Palette über einem anderen modalen Dialog | über dem MFA-Popup unterbunden; nach „Später" geht sie wieder auf und zu |
| Fokusring | `--focus-halo` (weißer Unterring) gilt jetzt auch für die dunkle Zusammenfassung, nicht nur für die Sidebar; Ringfarbe und Marken-Optik unverändert | berechneter Stil an Summary-Link, Sidebar und Hellgrund; Screenshot |
| Callback-Neuladen | Alle Effekt-Abhängigkeitslisten durchgesehen: außer dem Dashboard hängt kein Effekt von einer Funktion ab (alle `load()`-Effekte nur von `accessToken`/Skalaren). Messung: Palette dreimal öffnen/schließen löst auf 15 Seiten **0** zusätzliche Requests (ohne `/auth/me`) aus | 15 von 24 gemessenen Seiten; die übrigen 9 (Erste Schritte, Mahnungen, Ausgaben, Kassenbuch, Cashflow, SuSa, BWA, Datenumzug, Benutzer) sprengte die Mock-Antwortform, sie sind nur über die Listendurchsicht abgedeckt |

Nicht gelöst/Grenzen: „Meine Daten exportieren" (Owner-only im Backend) ist für Mitglieder auf der Sicherheitsseite weiterhin sichtbar und
liefert dort einen 403 (die Sicherheitsseite gehört dem parallelen Auth-Branch und wurde hier nicht angefasst).
Das Backend wurde nicht gestartet; die Tests dieser Arbeit gelten nur gegen den Mock.

## Gefunden, bewusst nicht behoben (Entscheidung oder Folgearbeit)

- **Rechnungsliste auf dem Handy:** Die Tabelle ist mit Mindestbreite 600 px gebaut, die Aktionsspalte (PDF, E-Mail, Finalisieren …) liegt auf 390 px außerhalb des Bildes und ist nur durch seitliches Wischen erreichbar, ohne sichtbaren Hinweis. Ein
  Kartenlayout wäre eine größere Designentscheidung. Gilt analog für andere Listen (Angebote, Produkte …).
- Startfokus nach Schließen des MFA-Popups ohne „Jetzt einrichten": Fokus liegt auf `body` (der Dialog öffnet sich beim Laden, es
  gab keinen vorherigen Fokus, den man wiederherstellen könnte).
- Nach „MFA einrichten" auf der Sicherheitsseite geht der Fokus verloren (Button verschwindet). Bewusst nicht auf das Codefeld
  gesetzt, damit auf dem Handy nicht sofort die Tastatur das Secret verdeckt.
- ~~Strg+K öffnet die Suchpalette auch über dem MFA-Popup~~ **Behoben** (Folgearbeit, s. u.).
- ~~`MfaEnrollment.tsx` und der Schritt `mfa-enroll` sind toter Code~~ **Entfernt** (Folgearbeit, s. u.).
- ~~Weitere Seiten könnten dasselbe Muster „Effekt hängt von instabiler Callback-Funktion ab" haben~~ **Geprüft** (Folgearbeit, s. u.).
- ~~Fokus-Token `--focus` ist auf dunklem Primärgrün zu schwach~~ **Behoben** über `--focus-halo` (Folgearbeit, s. u.).
- Der Dateiauswahl-Text („Choose File / No file chosen") folgt der Browsersprache; im deutschsprachigen Browser lokalisiert.

## Ausdrücklich nicht geprüft

- **Safari / iOS**, **Firefox**, **Android-Chrome** und **echte Geräte** (Touch-Gesten, Tastatur-Einblendung, Safe-Areas, Notch,
  Scroll-Verhalten, `100dvh`). Nur Chrome for Testing 151 (Linux, headless) mit fester Fensterbreite.
- **PWA-Installation** (Manifest, Service Worker, Installierbarkeit, Offline-Start der installierten App): erfordert HTTPS auf
  der echten Domain. Der Service Worker wird im Entwicklungsmodus gar nicht registriert. Nur der Offline-Fehlerzustand beim Start wurde
  mit gemocktem Netzfehler geprüft.
- **Echter E-Mail-Versand** (SMTP), **echte PDF-Erzeugung**, echte OCR, echter
  Datenexport-Download.
- **Ende-zu-Ende gegen das echte Backend** (Antwortformen, Fehlertexte, Statuscodes). Fehlertexte der Mocks sind
  ausgedacht. Kernfluss Punkt 3–10 der früheren Release-Planung (Kontakt → Rechnung → PDF → Versand → Zahlung, OCR-Beleg, Angebot →
  Rechnung, DATEV, Löschworkflow, Mitarbeiter anlegen) wurde **nicht** funktional durchgespielt, nur die Seiten und
  Formulare darstellungsseitig.
- Bildschirmleser (NVDA/VoiceOver/TalkBack): nur strukturell (Rollen, Namen, Labels), nie mit einem echten Screenreader.
- Dunkelmodus (existiert laut Projektkontext nicht), Druckansicht, Browser-Zoom 200 %/Textgrößen-Änderung, `prefers-reduced-motion`.
- Lasttest, Performance, Netzwerkdrosselung.
