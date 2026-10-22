# Spec: Handykamera und E-Mail-Eingang

Status: Kamera GEBAUT (Phase D1). E-Mail-Eingang OFFEN (Phase D2, blockiert bis zur Wahl des
Mail-Anbieters und bis DNS steht).

## D1 Kamera

- Im Beleg-Upload gibt es einen Button "Foto aufnehmen" (`<input type="file" capture="environment">`).
  Auf dem Handy öffnet er direkt die Kamera, am Desktop den Dateiauswähler.
- Bilder werden vor dem Upload im Browser verkleinert (`frontend/src/lib/bild.ts`):
  längste Kante 2400 px, JPEG mit 85 % Qualität, EXIF-Ausrichtung wird angewendet. Handykameras
  liefern 10 bis 20 MB, für die Texterkennung reicht ein Bruchteil. Das gilt für alle Bilder im
  Upload, nicht nur für Kamerafotos.
- Unverändert bleiben: kleine Bilder (höchstens 3 MB und höchstens 2400 px), PDF, XML und alles, was
  der Browser nicht dekodieren kann. Ist das verkleinerte Bild nicht kleiner als das Original,
  wird das Original hochgeladen.
- Beim Verkleinern wird transparenter Hintergrund weiß (JPEG kennt keine Transparenz).
- Nebenbei behoben: "Trotzdem als neuen Beleg hochladen" nach einer Duplikat-Meldung nutzt jetzt
  die zuletzt gewählte Datei, auch bei einem Kamerafoto.

### Annahmen

- Nur im Browser mit künstlich erzeugten Bildern geprüft, nicht mit echten Handyfotos und nicht
  auf einem Handy. Verhalten von `capture` unterscheidet sich je nach Gerät und Browser.
- Ein Foto je Beleg. Mehrseitige Belege (mehrere Fotos zu einem PDF) gibt es nicht.
- Keine Bildverbesserung (Entzerren, Zuschneiden). Schlechte Fotos bleiben schlecht lesbar.

## D2 E-Mail-Eingang (offen)

Geplant, siehe Feature-Plan: Adresse `belege+<token>@<domain>` je Mandant, Dienst
`python -m app.inbound.poll` (IMAP über TLS), Prüfung von Token und Absender (Mitglieder oder
bestandenes SPF/DKIM), nur erlaubte Anhangstypen, max. 10 Anhänge und 15 MB, Erfassung über
`erfasse_beleg(..., quelle="email")`, Mailtext wird nicht gerendert oder gespeichert, Audit
`beleg_per_email`.

Voraussetzungen, die nur du klären kannst: Mail-Anbieter, MX/SPF/DKIM-Einträge, Postfach mit
IMAP-Zugang. Dazu gehören Anpassungen in Datenschutzerklärung und AVV (Mail-Anbieter als
Unterauftragsverarbeiter, Verarbeitung von Mailanhängen).
