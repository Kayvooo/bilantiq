# Spec: behobene Laufzeit-Abhängigkeiten in den Sicherheitsimages

## Annahmen, die ich getroffen habe

- Sicherheitspflege umfasst gezielte Updates der bestehenden Laufzeit, ohne Rollen-/MFA-/Parser-Architektur umzubauen.
- Python bleibt in der Reihe 3.14. Debian trixie ersetzt bookworm, damit neuere gepflegte native Bibliotheken verfügbar sind.
- Pillow 13.0.0 behebt die vom Image-Scan gemeldeten Bildbibliotheksprobleme. Die inkompatiblen Änderungen wurden gegen
  die verwendeten APIs geprüft; vollständige Tests müssen die Kompatibilität zusätzlich belegen.
- Die API installiert im Betrieb keine Pakete. pip, seine vendorten Bibliotheken und ensurepip gehören nur zum Build.
- Caddy bleibt 2.11.7 mit Standardmodulen. Der Upstream-Binärbuild enthält ältere Go-/x/net-Versionen; deshalb erfolgt
  ein gezielter Neubau mit Go 1.27.3 und x/net 0.60.0. Keine zusätzlichen Plugins oder geänderte Proxy-Konfiguration.

## Änderungen und Nachweise

- Backend: offizielles `python:3.14.9-slim-trixie`, aktuelle apt-Pakete, Pillow 13.0.0, keine Paketinstaller im Laufzeitimage.
- Frontend: Standard-Caddy-Einstiegspunkt mit festem Caddy-Modul, repariertem x/net und festem Go-Compiler. Der
  offizielle Caddy-Runtime-Aufbau bleibt erhalten; nur die Binärdatei wird ersetzt.
- Maschinenlesbare Scannerberichte und SBOMs als CI-Artefakte. High/Critical bleiben Fehler; keine pauschalen Ausnahmen.
- Native OCR-/Bild-/PDF-Smoke-Prüfung im gebauten Backend-Image, Caddy-Konfigurationsprüfung im gebauten Frontend-Image.
- Vollständige Backend-Suiten einschließlich PostgreSQL, Frontend-Build und beide Compose-Startketten erneut ausführen.

## Grenzen

Ein höherer Versionsstand allein beweist keine vollständige Sicherheit. Aktueller Image-Scan, Regressionstests und
Betriebsabnahme bleiben erforderlich. Basisimages sind auf Versionen und Registry-Digests festgelegt
(`security-dependency-pins.md`); apt-Pakete werden weiterhin aus aktuellen signierten Repositories installiert.
Neue Scannerbefunde müssen einzeln bewertet werden. Claude-Pakete F2 bis F7 bleiben separat.

Die Abnahme für `d2608032` ist in `../security-image-befunde.md` dokumentiert: Laufzeit-/Regressionstests und
Frontend-Image bestehen, der Backend-Image-Job bleibt wegen offener Debian-Befunde gesperrt.
