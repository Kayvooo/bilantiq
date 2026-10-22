# Lokale KI-Roadmap für Bilantiq

Status: PLANUNG — keine der hier beschriebenen KI-Funktionen ist durch diese Spec bereits gebaut.

## Ziel

Bilantiq soll KI dort einsetzen, wo semantische Interpretation Arbeit spart, während
Beträge, Steuerberechnungen, Buchungsregeln, Berechtigungen und finale Schreibvorgänge
deterministisch im bestehenden FastAPI-Backend bleiben. Kundendaten sollen für die
geplante Standardkonfiguration nicht an externe LLM-APIs übertragen werden.

## Architekturprinzip

```
Frontend
   |
FastAPI
   |-- Postgres
   |-- bestehende Fachlogik
   |
   +--> interner AI-Client
           |
           +--> lokaler OpenAI-kompatibler Inference-Service
                    |
                    +--> austauschbares Modell
```

Der Inference-Service bekommt keinen Datenbankzugriff und keinen öffentlichen Port.
FastAPI entscheidet explizit, welche Daten in einen Prompt gelangen. Modellantworten
werden über Pydantic-Schemas validiert. Schreibende Aktionen erfordern weiterhin die
bestehenden Routen und Berechtigungsprüfungen.

## Phase A — Provider-Abstraktion

Neues Paket:

```
backend/app/ai/
  client.py
  config.py
  schemas.py
  prompts.py
  tools.py
```

Konfiguration:

- AI_ENABLED
- AI_BASE_URL
- AI_MODEL
- AI_TIMEOUT_SECONDS

Kein provider-spezifischer Code in Fachmodulen. Der Client spricht eine
OpenAI-kompatible lokale API, sodass Modelle/Inference-Server austauschbar bleiben.

Akzeptanzkriterien:
- kein externer Netzwerk-Fallback;
- Timeouts führen zu normalem, erklärbarem Fallback;
- strukturierte JSON-Ausgabe wird strikt validiert;
- keine Secrets oder vollständigen DB-Objekte im Prompt-Logging.

## Phase B — Lieferantenlernen vor LLM

Neue mandantengetrennte Tabelle `buchungsregeln`:

- id
- mandant_id
- anbieter_normalisiert
- kategorie
- konto
- bestaetigungen
- zuletzt_verwendet

Beim bestätigten Beleg wird eine Nutzerkorrektur als Regel gelernt. Reihenfolge für
künftige Vorschläge:

1. bestätigte Lieferantenregel;
2. bestehende deterministische Keywords/Kontenrahmen;
3. lokales LLM nur wenn weiterhin unsicher;
4. Nutzerbestätigung.

Keine mandantenübergreifenden Regeln.

## Phase C — Hybrid-Belegerkennung

Bestehendes Tesseract bleibt erste Stufe. Das lokale Modell wird nur bei Feldern unter
der Confidence-Schwelle oder bei komplexen Dokumenten aufgerufen.

Zieloutput:

```json
{
  "anbieter": {"wert": "...", "confidence": 0.0},
  "betrag": {"wert": "0.00", "confidence": 0.0},
  "datum": {"wert": "YYYY-MM-DD", "confidence": 0.0},
  "steueranteile": [
    {"ust_satz": "19.00", "bruttobetrag": "119.00"}
  ],
  "kategorie": "...",
  "konto": "...",
  "begruendung": "..."
}
```

Bilantiq validiert:
- Summe der Steueranteile = Gesamtbetrag;
- nur unterstützte Steuersätze;
- Konto muss aus freigegebenem Kontenrahmen stammen;
- kein automatisches Buchen.

## Phase D — Read-only Bilantiq-Assistent

Der Assistent erhält keine freie SQL-Schnittstelle. Er darf nur definierte,
mandantengetrennte Tools aufrufen, zunächst ausschließlich lesend:

- get_dashboard(jahr)
- get_euer(jahr)
- get_ustva(jahr, zeitraum)
- get_bwa(jahr)
- get_susa(jahr)
- get_cashflow(wochen)
- list_offene_rechnungen()
- list_ueberfaellige_rechnungen()
- list_ausgaben(von, bis)
- list_ausgaben_nach_kategorie(von, bis)

Das Modell formuliert Erklärungen; Zahlen stammen ausschließlich aus den bestehenden
deterministischen Berechnungen.

## Phase E — Entwürfe aus natürlicher Sprache

Erlaubte Schreibfunktion zuerst nur für Entwürfe:

- Rechnungsentwurf erstellen
- Angebotsentwurf erstellen

Das Modell erzeugt ein validiertes Schema, das über dieselben bestehenden
Create-Strukturen läuft. Es darf niemals Rechnungen finalisieren, Nummern vergeben,
Zahlungen markieren oder Belege automatisch buchen.

## Phase F — Textassistenz

Niedrigeres Risiko, daher nach dem Kernassistenten:

- Rechnungsbegleittext;
- Angebotsmail;
- Zahlungserinnerung/Mahnung;
- Textvorlagen.

Versand bleibt immer eine separate Nutzeraktion über die bestehende SMTP-Logik.

## Phase G — Bankabgleich (separate Produktentscheidung)

Erst nach einer echten Bankanbindung. LLM nur als Ranking-/Erklärschicht:

1. deterministisches Matching über Betrag, Verwendungszweck, IBAN, Datum;
2. lokales Modell nur bei mehreren plausiblen Kandidaten;
3. Nutzer bestätigt;
4. bestehende Zahlungslogik verbucht.

Kein LLM darf Bankbewegungen erfinden oder ohne Regelprüfung zuordnen.

## Datenschutz/Sicherheit

- Standardbetrieb lokal/self-hosted.
- AI-Container intern, nicht öffentlich erreichbar.
- möglichst kein ausgehender Internetzugriff aus dem Inference-Netz.
- keine Trainingsnutzung von Kundendaten ohne separate, ausdrückliche Produktentscheidung.
- keine Prompt-/Response-Rohdaten dauerhaft loggen.
- Audit-Log erfasst AI-Vorschlag verwendet/abgelehnt, aber keine unnötigen
  personenbezogenen Promptinhalte.
- Mandantentrennung wird vor Tool-/Prompt-Erzeugung im Backend erzwungen.
- DSGVO-Datenexport muss neue persistierte Lernregeln einschließen.
- Lösch-/Aufbewahrungslogik muss für neue AI-Metadaten definiert werden.

## Priorisierung

P0:
1. aktuelle Beleg-/Steuerdatenbasis stabilisieren;
2. Provider-Abstraktion;
3. Lieferantenlernen.

P1:
4. Hybrid-Belegerkennung;
5. lokaler Buchungsvorschlag.

P2:
6. read-only Bilantiq-Assistent;
7. Rechnungs-/Angebotsentwürfe aus Sprache.

P3:
8. Textassistenz;
9. Bankabgleich nach Bankintegration.

## Modellwahl

Nicht in Fachcode fest verdrahten. Vor Auswahl Benchmark mit einem Bilantiq-eigenen,
anonymisierten Testset:

- deutsche Kassenbons;
- Eingangsrechnungen;
- gemischte 7/19-%-Belege;
- schwierige Scans;
- 50-100 Buchungskategorisierungen;
- 30 Tool-Calling-Fragen über EÜR/UStVA/BWA/offene Rechnungen.

Metriken:
- Feldgenauigkeit;
- JSON-/Schema-Fehlerrate;
- falsche Kontovorschläge;
- Halluzinationsrate bei Zahlen;
- Latenz;
- RAM/VRAM;
- Durchsatz bei parallelen Mandanten.

Erst danach Modell/Quantisierung festlegen.
