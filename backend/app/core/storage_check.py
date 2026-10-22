"""Startpruefung fuer den Dateispeicher einer selbst betriebenen Instanz.

Alle Dateien (Belege, Logos, Briefpapier, Kontoauszuege, Altrechnungs-Archiv) liegen unter ``STORAGE_DIR``
(Standard ``./data``). Jede Person, die Bilantiq betreibt, braucht dafuer einen eigenen, dauerhaften Speicher
(Docker-Volume, Bind-Mount oder lokaler Ordner). Es gibt keinen zentralen Speicher des Projekts.

Diese Pruefung laeuft beim Start der App (``app/main.py``) und kann vorab als Kommando laufen::

    python -m app.core.storage_check

Sie legt fehlende Ordner mit den Rechten 0700 an, prueft mit einer echten Probedatei, dass geschrieben werden kann,
und meldet jedes Problem als lesbare Zeile statt als Stacktrace. Zu weite Rechte (Gruppe/Andere) werden auf 0700
zurueckgesetzt, sofern der Prozess der Besitzer ist; sonst gibt es nur eine Warnung. Die Dateien selbst sind
zusaetzlich per AES-256-GCM verschluesselt (``app/core/secure_storage.py``) und werden dort mit 0600 geschrieben.

Grenzen: Die Pruefung sagt nichts ueber Ausfallsicherheit, Backups oder Verschluesselung des Datentraegers.
Das bleibt Sache des Betreibers (docs/self-hosting.md).
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

MIN_FREIER_PLATZ_MB = 200


class SpeicherFehler(RuntimeError):
    """Der Dateispeicher ist nicht benutzbar. Die Meldung ist fuer Betreiber gedacht und enthaelt die Abhilfe."""


@dataclass
class Speicherpruefung:
    ordner: list[Path] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


def speicherordner() -> list[tuple[str, str]]:
    """Name und konfigurierter Pfad aller Speicherordner (Basisordner zuerst)."""
    return [
        ("Basisordner (STORAGE_DIR)", settings.storage_dir),
        ("Belege", settings.receipt_storage_dir),
        ("Logos", settings.branding_storage_dir),
        ("Briefpapier", settings.letterhead_storage_dir),
        ("Kontoauszüge", settings.bank_storage_dir),
        ("Altrechnungen", settings.altrechnung_storage_dir),
    ]


def _pruefe_ordner(name: str, pfad: str, ergebnis: Speicherpruefung, fehler: list[str]) -> None:
    ordner = Path(pfad).expanduser()
    try:
        absolut = ordner.resolve()
    except OSError as exc:
        fehler.append(f"{name}: Der Pfad '{pfad}' lässt sich nicht auflösen ({exc.strerror or type(exc).__name__}).")
        return

    if absolut.exists() and not absolut.is_dir():
        fehler.append(f"{name}: '{absolut}' existiert, ist aber kein Ordner. Bitte STORAGE_DIR auf einen Ordner setzen.")
        return
    if not absolut.exists():
        try:
            absolut.mkdir(parents=True, mode=0o700, exist_ok=True)
        except PermissionError:
            fehler.append(
                f"{name}: '{absolut}' existiert nicht und kann nicht angelegt werden (keine Berechtigung). "
                "Ordner anlegen und dem Benutzer gehören lassen, unter dem Bilantiq läuft (im Docker-Image UID 1000), "
                "oder STORAGE_DIR auf einen beschreibbaren Ordner setzen."
            )
            return
        except OSError as exc:
            fehler.append(f"{name}: '{absolut}' kann nicht angelegt werden ({exc.strerror or type(exc).__name__}).")
            return

    # Echte Probedatei: os.access() sagt bei Netzlaufwerken und read-only gemounteten Volumes nicht immer die Wahrheit.
    probe = absolut / f".schreibtest-{uuid.uuid4().hex}"
    try:
        fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, b"ok")
        finally:
            os.close(fd)
        os.remove(probe)
    except OSError as exc:
        fehler.append(
            f"{name}: In '{absolut}' kann nicht geschrieben werden ({exc.strerror or type(exc).__name__}). "
            "Prüfe Besitzer und Rechte des Ordners bzw. ob das Volume schreibgeschützt eingebunden ist "
            "(im Docker-Image läuft Bilantiq als UID 1000)."
        )
        try:
            os.remove(probe)
        except OSError:
            pass
        return

    modus = stat.S_IMODE(absolut.stat().st_mode)
    if modus & 0o077:
        try:
            os.chmod(absolut, 0o700)
        except OSError:
            ergebnis.warnungen.append(
                f"{name}: '{absolut}' hat die Rechte {modus:04o} (Gruppe/Andere dürfen zugreifen) und konnte nicht auf 0700 "
                "gesetzt werden. Bitte als Besitzer des Ordners `chmod 700` ausführen."
            )
    ergebnis.ordner.append(absolut)


def pruefe_speicher() -> Speicherpruefung:
    """Legt die Speicherordner an und prueft sie. Wirft SpeicherFehler mit allen gefundenen Problemen."""
    ergebnis = Speicherpruefung()
    fehler: list[str] = []
    for name, pfad in speicherordner():
        _pruefe_ordner(name, pfad, ergebnis, fehler)
    if fehler:
        raise SpeicherFehler(
            "Der Dateispeicher ist nicht benutzbar:\n  - " + "\n  - ".join(fehler)
            + "\nSiehe docs/self-hosting.md, Abschnitt Speicher."
        )
    if ergebnis.ordner:
        try:
            frei_mb = shutil.disk_usage(ergebnis.ordner[0]).free // (1024 * 1024)
            if frei_mb < MIN_FREIER_PLATZ_MB:
                ergebnis.warnungen.append(
                    f"Auf dem Datenträger von '{ergebnis.ordner[0]}' sind nur noch {frei_mb} MB frei."
                )
        except OSError:
            pass
    return ergebnis


def main() -> int:
    """Kommandozeile: gibt eine Meldung aus und liefert Exit-Code 0 (in Ordnung) oder 1 (Problem), ohne Stacktrace."""
    try:
        ergebnis = pruefe_speicher()
    except SpeicherFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1
    for warnung in ergebnis.warnungen:
        print(f"WARNUNG: {warnung}", file=sys.stderr)
    print(f"Dateispeicher in Ordnung ({settings.storage_dir}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
