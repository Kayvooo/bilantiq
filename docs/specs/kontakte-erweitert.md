# Spec: Kontakte erweitert (Lieferanten, Ansprechpartner, Zahlung, Leitweg-ID)

Status: GEBAUT (Branch `feature/datenumzug`, Phase 1 des Plans Datenumzug).

## Problem

Kontakte kannten nur Kunden mit Adresse. Fremdexporte (lexoffice, sevdesk, Excel) enthalten
fast immer Ansprechpartner, Telefon, IBAN und Zahlungsbedingungen, die beim Import sonst
verloren gingen. Behörden verlangen in der XRechnung ihre Leitweg-ID, die XRechnung schrieb
aber gar keine Käuferreferenz (BT-10), obwohl XRechnung sie immer verlangt (BR-DE-15).

## Verhalten

- **Art:** Kunde, Lieferant oder beides. Rechnungen, Angebote und Vorlagen bieten nur Kunden
  (und "beides") zur Auswahl an.
- **Neue Felder:** Anrede, Vorname, Nachname, Telefon, Notiz, Steuernummer, IBAN, BIC,
  Zahlungsziel in Tagen, Skonto (Prozent und Tage), Leitweg-ID. Alle Textfelder verschlüsselt.
  Produkte haben eine Artikelnummer.
- **Prüfung** (`app/core/validierung.py`, nur bei Eingaben, nie beim Lesen von Altbestand):
  - IBAN: Format, 22 Stellen bei DE, Prüfziffer (Modulo 97). Gespeichert ohne Leerzeichen.
  - BIC: 8 oder 11 Zeichen.
  - USt-IdNr.: Formatregel je Land (DE, AT, BE, CH, CZ, DK, ES, FR, IT, LU, NL, PL, SE), sonst
    nur "Länderkürzel plus 2 bis 13 Zeichen". Leer- und Trennzeichen werden entfernt.
  - Leitweg-ID: Grobadressierung (2 bis 12 Ziffern), optional Feinadressierung (bis 30
    Zeichen), Prüfziffer (2 Ziffern, Modulo 97-10).
  - Leere Eingaben werden zu "nicht gesetzt".
- **Archivieren statt Löschen:** Archivierte Kontakte verschwinden aus Listen und Auswahlen,
  bleiben aber für bestehende Rechnungen erhalten. Löschen geht nur, wenn kein Dokument
  (Rechnung, Angebot, Auftragsbestätigung, Lieferschein, wiederkehrende Rechnung) auf den
  Kontakt zeigt, sonst 409 mit Hinweis auf Archivieren. Löschen steht im Audit-Log
  (`kontakt_geloescht`).
- **Rechnungseditor:** Bei der Kontaktwahl kommt das Zahlungsziel aus dem Kontakt (sonst aus
  den Buchhaltungseinstellungen), Skonto wird vorbelegt. Hat der Kontakt eine Leitweg-ID,
  erscheint ein Hinweis.
- **XRechnung:** `cbc:BuyerReference` direkt nach `DocumentCurrencyCode` aus Leitweg-ID,
  sonst Kundennummer, sonst Rechnungsnummer.
- **Kontoauszug-Abgleich:** Die IBAN der Gegenpartei wird über einen Blind-Index
  (`kontakte.iban_hash`) mit Kontakten verglichen. Eingang: bekannte IBAN des Rechnungskunden
  gibt Zusatzpunkte ("IBAN bekannt"), macht einen Vorschlag aber nie allein "sicher".
  Ausgang: IBAN eines Lieferanten, dessen Name zum Anbieter des Belegs passt, zählt wie ein
  passender Name ("IBAN gehört zu Lieferant ...").
- **Oberfläche:** Kontakte-Seite mit Reitern Alle, Kunden, Lieferanten, Archiv und Suche
  (Name, Ort, PLZ, E-Mail, Nummer, Telefon, Ansprechpartner). Formular mit aufklappbaren
  Abschnitten. Das Formular im Rechnungseditor ist jetzt dasselbe wie auf der Kontakte-Seite.

## Technik

- Migration `0032` (Spalten an `kontakte` und `produkte`, Index auf `iban_hash`).
- `app/invoices/kontakte.py`: `kontakt_iban_hash`, `setze_iban`, `kontakt_wird_verwendet`.
- Endpunkte: `GET /kontakte?typ=kunde|lieferant&archiviert=true`,
  `POST /kontakte/{id}/archivieren`, `POST /kontakte/{id}/wiederherstellen`,
  `DELETE /kontakte/{id}`.
- Schlüsselrotation: neue Spalten plus bisher fehlende `kontakt.land` und `produkt.einheit`.
- DSGVO-Datenexport enthält die neuen Felder automatisch, `iban_hash` nicht.

## Annahmen, die ich getroffen habe

- **Leitweg-ID-Prüfziffer:** Modulo 97-10 nach ISO 7064, geprüft an zwei mir bekannten
  Beispiel-IDs (`04011000-1234512345-06`, `04011000-12345-03`). Nicht gegen die offizielle
  Spezifikation oder den KoSIT-Validator geprüft.
- **BT-10 ohne Leitweg-ID:** Kundennummer, sonst Rechnungsnummer. Das erfüllt die Pflicht,
  ein Feld zu füllen. Ob Empfänger damit etwas anfangen, ist offen.
- **USt-IdNr.:** Nur das Format, nicht die Vergabe (dafür bräuchte es BZSt oder VIES).
- Archivierte Kontakte können weiterhin per API für Rechnungen verwendet werden (z. B.
  Korrekturrechnungen), die Oberfläche bietet sie nur nicht an.
