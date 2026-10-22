"""Reject stale direct requirements and divergent runtime/development locks."""
from __future__ import annotations

import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def read_requirements(path: Path, *, hashed: bool) -> dict:
    entries = {}
    logical = ""
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        continuation = line.endswith("\\")
        logical += (line[:-1] if continuation else line) + " "
        if continuation:
            continue
        if logical.startswith("-r "):
            # The only source include is the runtime input in requirements-dev.txt.
            if hashed or logical.strip() != "-r requirements.txt":
                raise ValueError(f"Unerwarteter Include in {path.name}")
            for key, value in read_requirements(path.parent / "requirements.txt", hashed=False).items():
                entries[key] = value
            logical = ""
            continue
        hashes = re.findall(r"\s+--hash=sha256:([0-9a-f]{64})(?=\s|$)", logical)
        requirement = Requirement(re.sub(r"\s+--hash=sha256:[0-9a-f]{64}(?=\s|$)", "", logical).strip())
        pins = list(requirement.specifier)
        if requirement.url or len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise ValueError(f"Keine exakte Version fuer {requirement.name} in {path.name}")
        if hashed and not hashes:
            raise ValueError(f"SHA-256 fehlt fuer {requirement.name} in {path.name}")
        key = (canonicalize_name(requirement.name), str(requirement.marker or ""))
        if key in entries:
            # Repeated direct declarations are valid only with identical pins/extras.
            if str(entries[key].specifier) != str(requirement.specifier) or entries[key].extras != requirement.extras:
                raise ValueError(f"Widerspruechliche Anforderung {requirement.name} in {path.name}")
        entries[key] = requirement
        logical = ""
    if logical:
        raise ValueError(f"Unvollstaendige Fortsetzung in {path.name}")
    return entries


def check_locks(root: Path) -> None:
    runtime = read_requirements(root / "requirements.lock", hashed=True)
    development = read_requirements(root / "requirements-dev.lock", hashed=True)
    for source, locked in (("requirements.txt", runtime), ("requirements-dev.txt", development)):
        for key, direct in read_requirements(root / source, hashed=False).items():
            selected = locked.get(key)
            if (selected is None or str(selected.specifier) != str(direct.specifier)
                    or not direct.extras.issubset(selected.extras)):
                raise ValueError(f"Lock passt nicht zu {direct.name} aus {source}; beide Locks erneuern.")
    runtime_names = {key[0] for key in runtime}
    if {key for key in development if key[0] in runtime_names} != set(runtime):
        raise ValueError("Plattformbedingungen der Laufzeit-/Dev-Locks weichen ab.")
    for key, selected in runtime.items():
        other = development[key]
        if str(selected.specifier) != str(other.specifier) or selected.extras != other.extras:
            raise ValueError(f"Laufzeit-/Dev-Lock weichen bei {selected.name} ab.")


def main() -> int:
    try:
        check_locks(Path(__file__).resolve().parents[1])
    except (OSError, ValueError) as exc:
        print(f"Abhaengigkeitspruefung fehlgeschlagen: {exc}")
        return 1
    print("Direkte Anforderungen, SHA-256-Pins und Laufzeit-/Dev-Locks stimmen ueberein.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
