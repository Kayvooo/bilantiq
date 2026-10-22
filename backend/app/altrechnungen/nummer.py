"""Rechnungsnummern aus dem Altsystem vergleichen. Zwei Nummern gelten als gleich, wenn Ziffern und Buchstaben
uebereinstimmen, egal welche Trennzeichen dazwischen stehen ("RE-2024-1" = "RE 2024 1")."""
from __future__ import annotations

import re

from app.core.key_management import blind_index


def alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def nummer_hash(mandant_id: str, nummer: str) -> str:
    return blind_index(alnum(nummer), purpose=f"altrechnung-nummer:{mandant_id}")


def laufnummer_im_jahr(nummer: str, jahr: int, praefix: str = "RE") -> int | None:
    """Die Laufnummer, wenn `nummer` wie eine Bilantiq-Rechnungsnummer des Jahres aussieht (RE-2026-0150, auch
    "RE 2026 150" oder "RE2026150"), sonst None. Fuehrende Nullen zaehlen nicht."""
    treffer = re.fullmatch(rf"{re.escape(praefix.casefold())}{jahr}0*(\d+)", alnum(nummer))
    return int(treffer.group(1)) if treffer else None
