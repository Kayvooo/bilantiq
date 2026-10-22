#!/usr/bin/env python3
"""Einmalige Migration bestehender Upload-Dateien auf AES-256-GCM.

Kann sicher mehrfach ausgefuehrt werden: bereits verschluesselte Dateien werden
uebersprungen. Vor Produktion zuerst Backup erstellen und anschliessend die normalen
Smoke-/Regressionstests ausfuehren.
"""
from app.config import settings
from app.core.secure_storage import reencrypt_tree


def main() -> None:
    targets = [
        ("Belege", settings.receipt_storage_dir, "receipt-file"),
        ("Logos", settings.branding_storage_dir, "branding-file"),
        ("Briefpapier", settings.letterhead_storage_dir, "letterhead-file"),
        ("Kontoauszüge", settings.bank_storage_dir, "bank-file"),
        ("Altrechnungen", settings.altrechnung_storage_dir, "altrechnung-file"),
    ]
    for name, root, purpose in targets:
        encrypted, skipped = reencrypt_tree(root, purpose_prefix=purpose)
        print(f"{name}: {encrypted} verschluesselt, {skipped} bereits verschluesselt")


if __name__ == "__main__":
    main()
