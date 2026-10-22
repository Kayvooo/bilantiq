# Spec: E-Rechnung empfangen

Status: GEBAUT (Branch `feature/belege-bank`, Phase B des Feature-Plans Belege und Bank).

## Problem

Seit 1.1.2025 müssen Unternehmen in Deutschland E-Rechnungen empfangen können. Bilantiq
erzeugte sie, nahm aber beim Beleg-Upload nur PDF und Bilder an. Eine XRechnung ließ sich
nicht hochladen, bei ZUGFeRD wurde das eingebettete XML ignoriert und das PDF per
Texterkennung geschätzt.

## Verhalten

- Upload akzeptiert jetzt `application/xml` (Erkennung über den Inhalt, siehe
  `docs/specs/kategorien-lernen.md`).
- **XML-Datei:** wird als XRechnung gelesen. Unterstützt sind UBL `Invoice` und CII
  `CrossIndustryInvoice`. Lässt sich die Datei nicht lesen, antwortet der Upload mit HTTP 400
  und einer verständlichen Meldung (kein Beleg wird angelegt).
- **PDF:** Enthält es einen Rechnungsdatensatz als Anhang (`factur-x.xml`,
  `zugferd-invoice.xml`, `xrechnung.xml` oder ein anderes `.xml` mit passendem
  Wurzelelement), wird dieser gelesen (`beleg_typ = zugferd`). Sonst oder bei einem
  unlesbaren Anhang bleibt es bei der Texterkennung (`beleg_typ = ocr`).
- **Gelesene Felder:** Rechnungsnummer (BT-1), Datum (BT-2), Fälligkeit (BT-9), Währung
  (BT-5), Rechnungssteller (BT-27), USt-IdNr. des Ausstellers (BT-31), Gesamtbetrag (BT-112,
  ersatzweise BT-115), IBAN (BT-84), Steueraufschlüsselung (BT-116 bis BT-119).
  Maschinenlesbare Felder haben Konfidenz 0.99.
- **Steuer:** Ein einzelner unterstützter Satz (0, 7, 19 %) wird als `ust_satz`
  vorgeschlagen. Mehrere Sätze werden zur Aufteilung (`steueranteile_vorschlag`, Brutto je
  Satz = Basis plus Steuer), die das Bestätigungsformular vorbelegt. Weicht die Summe vom
  Gesamtbetrag ab oder kommt ein nicht unterstützter Satz vor, steht ein Hinweis in der
  Antwort (`hinweise`).
- **Kategorie** kommt weiter aus Stichworten (Verkäufername und Positionsnamen), danach greift
  das Lernen aus Phase A.
- **Duplikate:** zusätzlich zum Datei-Hash über einen Blind-Index aus Aussteller und
  Rechnungsnummer (`dedupe_key`, je Mandant). Dieselbe Rechnung als XML und als
  ZUGFeRD-PDF wird als Duplikat gemeldet. `force` legt trotzdem neu an.
- **Original:** Die Datei bleibt unverändert und verschlüsselt gespeichert, das XML ist bei
  E-Rechnungen der Originalbeleg (GoBD). Der Abruf liefert XML immer als Download
  (`Content-Disposition: attachment`).
- Kein Tarif-Gate und kein Monats-Belegelimit mehr (früher zählte es aufs Limit).

## Technik

- `app/receipts/e_rechnung.py` (Parser), Einbindung in `app/receipts/service.py::erfasse_beleg`.
- XML wird nur über `app/core/xml_safe.py` gelesen: kein DOCTYPE, keine Entitäten, kein
  Netzwerk, 5 MB.
- Migration `0030`: `receipts.beleg_typ`, `rechnungsnummer`, `faelligkeit`, `iban`,
  `e_rechnung_daten` (verschlüsseltes JSON), `dedupe_key`.
- Datenexport enthält die neuen Felder, nicht den internen `dedupe_key`.
- Oberfläche: Upload nimmt `.xml` an, Liste zeigt "E-Rechnung", die Vorschau zeigt statt des
  Dokuments die Rechnungsdaten und einen Download des Original-XML.

## Annahmen, die ich getroffen habe

- **Gelesen, nicht geprüft.** Keine KoSIT-/Schematron-Validierung. Eine fehlerhafte, aber
  lesbare E-Rechnung wird trotzdem übernommen. Der Nutzer bestätigt jeden Beleg.
- **Nur gegen eigene und handgeschriebene Dateien getestet.** Echte Dateien von
  Lieferanten (andere Profile wie EXTENDED, Rechnungen mit Nachlässen, Vorauszahlungen) und
  die offizielle KoSIT-Testsuite fehlen offline. Sie sollten als Fixtures dazukommen.
- Gutschriften (Typ 381, `CreditNote`) werden nicht automatisch gelesen, sondern mit
  Hinweis abgewiesen.
- Rechnungen in anderer Währung als Euro übernehmen den Betrag nicht, sondern weisen darauf hin.
- ZUGFeRD 1.0 (`CrossIndustryDocument`) wird nicht gelesen und fällt auf die Texterkennung
  zurück.
- Eine lesbare Darstellung des XML als PDF ist ein Folgeschritt und wäre keine rechtsgültige
  Sichtbarmachung.
