# Spec: feste Artefakte für Backend und Container-Builds

## Annahmen, die ich getroffen habe

- F8 umfasst auch die bisher offenen Python-Hash-Locks und festgelegte Image-Digests.
- Die erforderlichen nativen OCR-/PDF-Pakete werden erhalten. Die SBOM weist unter anderem
  `poppler-utils -> libpoppler -> libgpgme -> gnupg` und `tesseract -> libarchive -> libxml2` aus.
  Ihre Entfernung ohne Ersatz würde Funktionen beschädigen; F4 bleibt eine separate Architekturänderung.
- Ein Pin ist eine überprüfbare Auswahl, keine Aussage über Schwachstellenfreiheit. Die Image-Schranke bleibt aktiv.
- Das bereits in CI verwendete pip-audit wird als Dev-Abhängigkeit mitgesperrt, damit seine Installation denselben
  Hash-Regeln folgt. Der Laufzeit-Lock enthält dieses Werkzeug nicht.
- Python 3.13 und 3.14 sowie Linux amd64/arm64 bleiben Zielplattformen; fehlende Wheels führen zu einem klaren Fehler.

## Technische Änderung

- Eingabedateien `requirements.txt`/`requirements-dev.txt` behalten die direkten Abhängigkeiten. Universelle Lockdateien
  legen auch transitive Versionen und SHA-256-Hashes fest; der Dev-Lock verwendet den Laufzeit-Lock als Constraint.
- Docker und CI installieren ausschließlich Wheels mit `--require-hashes --only-binary=:all:` aus den Lockdateien.
  Ein Prüfkommando erkennt abweichende direkte Versionsvorgaben und Unterschiede zwischen Laufzeit-/Dev-Lock.
- Build-Kontexte schließen lokale Umgebungsdateien, Datenbanken, Datenspeicher, Secret-/Backup-Verzeichnisse und
  Entwicklungs-/Installer-Caches aus. Erforderliche Quell- und Konfigurationsdateien bleiben im Kontext.
- Basisimages werden mit den in der erfolgreichen CI aufgelösten Digests festgelegt. Die CI prüft die unterstützten
  Plattformen der referenzierten Manifeste, bevor Images gebaut werden.
- Dokumentierter Update-Weg: direkte Versionen aktualisieren, Locks neu erzeugen, Hash-/Versionsdiff prüfen,
  Audits und vollständige Backend-/Deployment-Prüfungen ausführen. Keine automatische Freigabe neuer Digests.
- Audit-Schritte mit `tee` verwenden explizit `shell: bash`. GitHub startet die explizite Bash mit `-eo pipefail`;
  der implizite Shell-Standard garantiert das nicht. Ein negativer Pipeline-Test belegt die Fehlerweitergabe.

## Abnahme und Grenzen

Hashgeprüfte Installation in frischer Umgebung, Negativprüfung mit geändertem Hash, Drift-Prüfung und vollständige CI.
Die Versionsmatrix wird mit pip-Wheel-Auflösung für Python 3.13/3.14 und Linux amd64/arm64 geprüft. Tags und Digests
werden zusammen dokumentiert; apt-Pakete bleiben aus signierten aktuellen Distributions-Repositories und verhindern
einen Anspruch auf vollständig bitidentische Builds. Die 29 offenen Debian-CVEs sind damit nicht behoben.
