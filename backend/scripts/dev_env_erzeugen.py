"""Erzeugt eine lokale ``backend/.env`` mit frischen, zufaelligen Schluesseln (nur fuer Entwicklung und lokales Ausprobieren).

Aufruf im Ordner ``backend`` (funktioniert unter Windows, macOS und Linux)::

    python scripts/dev_env_erzeugen.py

Das Skript kopiert ``.env.example`` nach ``.env`` und ersetzt die Platzhalter-Secrets. Eine vorhandene ``.env`` wird nie
ueberschrieben (mit ``--neu`` nur nach ausdruecklicher Angabe). Die erzeugten Schluessel gehoeren zu Ihrer lokalen
Datenbank: Gehen sie verloren, sind die damit verschluesselten Daten nicht mehr lesbar. Fuer Produktion gilt stattdessen
``scripts/init-secrets.sh`` (docs/self-hosting.md).
"""
from __future__ import annotations

import argparse
import base64
import re
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND = Path(__file__).resolve().parents[1]


def _b64url_ohne_padding(n: int = 32) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(n)).decode().rstrip("=")


def erzeuge_werte() -> dict[str, str]:
    return {
        "JWT_SECRET": secrets.token_hex(32),
        "FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "EMAIL_LOOKUP_SECRET": secrets.token_hex(32),
        "DATA_ENCRYPTION_KEYS": "v1:" + _b64url_ohne_padding(32),
        "BLIND_INDEX_SECRET": secrets.token_urlsafe(48),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Erzeugt backend/.env mit frischen Schluesseln (nur lokal/Entwicklung).")
    parser.add_argument("--neu", action="store_true", help="vorhandene .env ueberschreiben (Daten der alten Schluessel werden unlesbar)")
    args = parser.parse_args(argv)

    vorlage = BACKEND / ".env.example"
    ziel = BACKEND / ".env"
    if not vorlage.exists():
        print(f"FEHLER: {vorlage} nicht gefunden. Bitte im Ordner 'backend' des Repositories ausfuehren.", file=sys.stderr)
        return 1
    if ziel.exists() and not args.neu:
        print(f"{ziel} existiert bereits und bleibt unveraendert. Mit --neu wuerde sie ersetzt (alte Schluessel gehen verloren).")
        return 0

    text = vorlage.read_text(encoding="utf-8")
    for name, wert in erzeuge_werte().items():
        text, anzahl = re.subn(rf"(?m)^{name}=.*$", lambda _m, n=name, w=wert: f"{n}={w}", text)
        if anzahl != 1:
            print(f"FEHLER: {name} steht nicht genau einmal in .env.example.", file=sys.stderr)
            return 1
    ziel.write_text(text, encoding="utf-8", newline="\n")
    try:
        ziel.chmod(0o600)
    except OSError:
        pass
    print(f"{ziel} erstellt. Die Datenbank (SQLite) und der Ordner 'data' entstehen beim ersten Start.")
    print("Nicht committen und nicht weitergeben. Fuer Produktion: scripts/init-secrets.sh (docs/self-hosting.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
