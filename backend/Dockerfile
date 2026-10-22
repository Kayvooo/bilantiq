# Produktions-Image fuer das Bilantiq-Backend (FastAPI/uvicorn).
FROM python:3.14.9-slim-trixie@sha256:b347e2dcbc7f0b6f9fb7182e9da6a187fb10ae715e0692518c1aed0eec94a700

# System-Abhaengigkeiten fuer die lokale Belegerfassung (OCR), siehe README:
# Tesseract inkl. deutschem Sprachpaket und Poppler fuers PDF-Rendering.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-deu poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock .
# Installer und deren vendorte Bibliotheken werden fuer die unveraenderliche Laufzeit nicht benoetigt.
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock \
    && python -m pip uninstall --yes pip setuptools \
    && rm -rf /usr/local/lib/python3.14/ensurepip /root/.cache/pip

COPY . .

# Python findet "app" und "scripts" (z. B. "python -m scripts.konto_wiederherstellen") auch dann, wenn ein Skript
# direkt aufgerufen wird.
ENV PYTHONPATH=/app

# Dateispeicher der Instanz: alle Belege, Logos, Briefpapier, Kontoauszuege und das Altrechnungs-Archiv liegen unter
# STORAGE_DIR. Im Betrieb wird hier ein dauerhaftes Volume eingehaengt (siehe docker-compose.prod.yml und
# docs/self-hosting.md); ohne Volume gehen die Dateien mit dem Container verloren.
ENV STORAGE_DIR=/app/data

# Datenverzeichnis anlegen und Ownership setzen, bevor der Nicht-Root-Nutzer uebernimmt. Ein frisches benanntes
# Volume erbt beim ersten Mount die Ownership dieses Verzeichnisses aus dem Image -- damit ist es fuer den
# app-Nutzer beschreibbar, ohne als root zu laufen. Ein Bind-Mount eines Host-Ordners erbt das NICHT: der Ordner
# muss dem Benutzer mit UID 1000 gehoeren (die Startpruefung meldet es, wenn nicht).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Zuerst der Speicher-Check (klare Meldung und Abbruch ohne Stacktrace, falls /app/data nicht beschreibbar ist),
# Migrationen laufen vorher im separaten Compose-Dienst "migrate" mit eigener Admin-Verbindung.
# Die API prueft ihre eingeschraenkten Datenbankrechte und startet erst danach.
# dann uvicorn hinter dem Reverse-Proxy (X-Forwarded-Proto/-For werden vertraut, da
# nur der interne Caddy-Container das Backend erreicht). --no-server-header entfernt den
# "Server: uvicorn"-Header (Software-Fingerabdruck).
CMD ["sh", "-c", "python -m app.core.runtime_security && python -m app.core.storage_check && python scripts/reencrypt_storage.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=* --no-server-header"]
