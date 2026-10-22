# Phase E–G: Lokale KI für Assistent, Entwürfe und Textassistenz

Status: GEBAUT — Aktivierung erfordert einen konfigurierten lokalen Inference-Service

## Ziel

Bilantiq bekommt drei lokal betreibbare KI-Funktionen, ohne die bestehende deterministische
Buchhaltungs- und Versandlogik an ein LLM abzugeben.

- **Phase E:** read-only Bilantiq-Assistent über freigegebene Backend-Tools.
- **Phase F:** Rechnungs- und Angebotsentwürfe aus natürlicher Sprache.
- **Phase G:** Textvorschläge für Rechnungs-, Angebots- und Mahnungs-E-Mails.

Die Standardarchitektur ist self-hosted. Das Backend spricht ausschließlich mit einem
konfigurierten OpenAI-kompatiblen Inference-Endpunkt. Es gibt keinen Cloud-Fallback.

## Sicherheitsgrenzen

1. Das Modell erhält keinen direkten Datenbankzugriff.
2. Das Modell darf kein SQL erzeugen oder ausführen.
3. Phase E ist ausschließlich lesend.
4. Phase F darf nur Objekte mit Status `entwurf` erzeugen.
5. Phase F darf keine Rechnungs-/Angebotsnummer vergeben und nicht finalisieren.
6. Phase G erzeugt nur Text. Versand erfolgt ausschließlich nach einer separaten
   Nutzeraktion über die bestehenden SMTP-Routen.
7. Jede Modellantwort wird mit Pydantic validiert.
8. Mandantentrennung wird vor jeder Tool-Ausführung bzw. vor jeder Kontextbildung im
   FastAPI-Backend erzwungen.
9. Keine Roh-Prompts/-Responses mit personenbezogenen Inhalten im Audit-Log.
10. Bei nicht erreichbarer lokaler KI gibt es einen klaren 503-Fehler; niemals einen
    externen Fallback.

## Technische Architektur

```
React/TypeScript
      |
      v
FastAPI /api
      |
      +---- bestehende Fachlogik / SQLAlchemy / Postgres
      |
      +---- app/ai/
              client.py       OpenAI-kompatibler lokaler Client
              schemas.py      strikte Request-/Response-Schemas
              tools.py        read-only Tool-Registry für Phase E
              prompts.py      Systemprompts / Ausgabegrenzen
              routes.py       /ai/*
                      |
                      v
              internes Inference-Netz
                      |
              lokales Modell
```

Konfiguration:

- `AI_ENABLED=false` als sicherer Default
- `AI_BASE_URL=http://ai:8000/v1`
- `AI_MODEL=<lokales Modell>`
- `AI_TIMEOUT_SECONDS=30`
- optional `AI_API_KEY` für interne Gateways

## Phase E — Read-only Bilantiq-Assistent

### API

`POST /ai/assistent`

Request:
- `frage`
- optional `jahr`

Ablauf:

1. Prüfen, dass `AI_ENABLED` gesetzt ist (ein Tarif-Gate gibt es nicht mehr).
2. LLM wählt genau ein freigegebenes Tool und strukturierte Argumente.
3. Backend validiert Toolname/Argumente.
4. Backend führt das Tool mandantengetrennt aus.
5. Ergebnis wird JSON-serialisiert an das Modell zurückgegeben.
6. Modell formuliert eine Antwort ausschließlich anhand dieser Daten.
7. Audit-Log speichert nur den Toolnamen, nicht Frage/Antwort.

Initiale Tools:

- `dashboard(jahr)`
- `euer(jahr)`
- `ustva(jahr, zeitraum_typ, periode)`
- `bwa(jahr)`
- `susa(jahr)`
- `cashflow(wochen)`
- `offene_rechnungen()`
- `ueberfaellige_rechnungen()`
- `ausgaben(von, bis)`
- `ausgaben_nach_kategorie(von, bis)`

Nicht erlaubt:
- freie SQL-Abfragen;
- Mutation;
- Versand;
- Finalisierung;
- Kontolöschung;
- Benutzeränderungen.

### Frontend

Eigene Seite **KI-Assistent** in der Desktop-Navigation und unter „Mehr“/Erweiterungen.
Einfacher Verlauf innerhalb der aktuellen Seite; zunächst keine persistente Chat-Historie.

## Phase F — Entwürfe aus natürlicher Sprache

### API

- `POST /ai/rechnungsentwurf`
- `POST /ai/angebotsentwurf`

Request:
- `anweisung`

Das Backend gibt dem Modell nur die für den Mandanten sichtbaren Kontakte sowie notwendige
Buchhaltungsvorgaben. Das Modell muss eine vorhandene `kontakt_id` verwenden.

Rechnungsentwurf wird gegen `InvoiceCreate`, Angebotsentwurf gegen `QuoteCreate`
validiert und **noch nicht gespeichert**. Der validierte Entwurf wird in das bestehende
Formular geladen. Erst die explizite Nutzeraktion „Als Entwurf speichern“ ruft die
vorhandene Create-Route auf.

Garantien:
- vor Nutzerfreigabe entsteht noch kein DB-Objekt;
- nach dem Speichern entsteht ausschließlich der normale `entwurf`-Status;
- keine Nummernvergabe;
- kein Versand;
- kein Finalize;
- bestehende Monatslimits und Mandantenprüfungen bleiben aktiv.

### Frontend

Auf Rechnungen und Angebote kommt ein optionales Panel:
- Freitext-Anweisung;
- „KI-Entwurf erstellen“;
- nach Erfolg werden die bestehenden Rechnungs-/Angebotsformulare vorausgefüllt;
- Nutzer prüft/ändert die Werte und speichert erst anschließend über den normalen Flow.

## Phase G — Textassistenz

### API

`POST /ai/textvorschlag`

Request:
- `art`: `rechnung` | `angebot` | `mahnung`
- `objekt_id`
- optional `ton`: `freundlich` | `neutral` | `bestimmt`
- optional `hinweis` des Nutzers

Backend lädt das Objekt mandantengetrennt und baut nur den notwendigen Kontext.

Response:
- `text`

Die Route versendet **nichts**.

### Frontend

Bei Rechnung, Angebot und Mahnung:
1. „KI-Text“ erzeugen.
2. Text in editierbarer Textarea anzeigen.
3. Nutzer kann ändern.
4. Separater Button „Mit diesem Text senden“ ruft erst dann die bestehende Versandroute auf.

## Fehlerverhalten

- `503`: AI deaktiviert / Inference-Service nicht erreichbar.
- `502`: ungültige oder nicht parsebare Modellantwort.
- `404`: Objekt/Kontakt gehört nicht zum Mandanten.
- `400`: fachlich ungültiger Entwurf oder ungültige Tool-Argumente.

## Tests

Backend:
- AI deaktiviert -> 503.
- fremder Mandant kann keine Daten über E/G abfragen.
- Assistant akzeptiert nur erlaubte Tools.
- Tool-Ergebnis wird mandantengetrennt erzeugt.
- Rechnungsentwurf erzeugt vor Nutzerfreigabe keinen DB-Datensatz.
- Angebotsentwurf erzeugt vor Nutzerfreigabe keinen DB-Datensatz.
- ungültige Kontakt-ID wird abgewiesen.
- Textvorschlag verschickt keine E-Mail.
- Mahntext kann nur für eigene Mahnung erzeugt werden.
- Fake-AI-Provider statt echtem Modell im Test.

Frontend:
- TypeScript-Build.
- Lint.
- Produktionsbuild.
- UI zeigt 503 verständlich an.
- Senden bleibt zweite explizite Aktion.

## Nicht Teil dieser Phase

- persistente Chat-Historie;
- Vektor-Datenbank/RAG;
- autonomes Buchen;
- autonomes Finalisieren;
- autonome E-Mail-Aktionen;
- Bankabgleich;
- Fine-Tuning mit Kundendaten.


## Umsetzungsstand

Gebaut auf `feature/belege-buchhaltungsfixes`:

- `app/ai/client.py`: OpenAI-kompatibler lokaler Client, kein Cloud-Fallback.
- `app/ai/tools.py`: feste read-only Tool-Registry.
- `POST /ai/assistent`: Phase E.
- `POST /ai/rechnungsentwurf` und `POST /ai/angebotsentwurf`: Phase F als Formular-Vorschlag vor Persistenz.
- `POST /ai/textvorschlag`: Phase G ohne Versandaktion.
- Frontend-Seite KI-Assistent, KI-Vorausfüllung für Rechnung/Angebot und editierbarer KI-Text-Composer.
- `AI_ENABLED=false` bleibt Default; ohne bewusst konfigurierte lokale Inferenz ist die Funktion nicht aktiv.

Regression am 7. Oktober 2026:
- Backend: **337 Tests bestanden**, inklusive Migrations-Regression und neuer KI-/Belegtests.
- Frontend: TypeScript, Lint und Produktionsbuild erfolgreich.
