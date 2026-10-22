import { useRef, useState } from "react";
import { ApiError } from "../auth/api";
import { downloadBlob } from "../invoices/downloadBlob";
import {
  importiere, importVorschau, ladeFehlerliste, ladeVorlage, macheImportRueckgaengig, pruefeImport,
  type ImportErgebnis, type ImportOptionen, type ImportVorschau, type Pruefbericht, type PruefZeile, type StammdatenZiel,
} from "./api";

interface Props {
  accessToken: string;
  ziel: StammdatenZiel;
  onFertig: () => void;
  onAbbrechen: () => void;
}

const BEGRIFFE = {
  kontakte: { einzahl: "Kontakt", mehrzahl: "Kontakte", titel: "Kontakte importieren" },
  produkte: { einzahl: "Produkt", mehrzahl: "Produkte", titel: "Produkte importieren" },
  rechnungen: { einzahl: "Rechnung", mehrzahl: "Rechnungen", titel: "Rechnungen aus dem alten Programm übernehmen" },
} as const;

const STATUS_LABEL: Record<PruefZeile["status"], string> = {
  neu: "Neu", ergaenzen: "Wird ergänzt", vorhanden: "Schon vorhanden", doppelt: "Doppelt in der Datei", fehler: "Fehler",
};

type Schritt = "datei" | "zuordnung" | "bericht" | "fertig";

function beispielWert(vorschau: ImportVorschau, spalte: string | undefined): string {
  if (!spalte) return "";
  const index = vorschau.kopfzeilen.indexOf(spalte);
  return vorschau.beispielzeilen.map((zeile) => zeile[index] ?? "").find((wert) => wert.trim()) ?? "";
}

export function ImportAssistent({ accessToken, ziel, onFertig, onAbbrechen }: Props) {
  const begriffe = BEGRIFFE[ziel];
  const inputRef = useRef<HTMLInputElement>(null);
  const [schritt, setSchritt] = useState<Schritt>("datei");
  const [datei, setDatei] = useState<File | null>(null);
  const [vorschau, setVorschau] = useState<ImportVorschau | null>(null);
  const [optionen, setOptionen] = useState<ImportOptionen>({ zuordnung: {}, dezimal: "komma", doppelte: "ueberspringen", fehlerhafte_auslassen: false, standard_ust_satz: "19", zahlungsziel_tage: 14, fehlende_kunden_anlegen: false });
  const [bericht, setBericht] = useState<Pruefbericht | null>(null);
  const [ergebnis, setErgebnis] = useState<ImportErgebnis | null>(null);
  const [rueckgaengig, setRueckgaengig] = useState<string>("");
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState("");

  async function ausfuehren<T>(aktion: () => Promise<T>, meldung: string): Promise<T | null> {
    setLaedt(true);
    setFehler("");
    try {
      return await aktion();
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : meldung);
      return null;
    } finally {
      setLaedt(false);
    }
  }

  async function dateiGewaehlt(gewaehlt: File, blatt?: string | null) {
    setDatei(gewaehlt);
    const antwort = await ausfuehren(() => importVorschau(accessToken, ziel, gewaehlt, blatt), "Die Datei konnte nicht gelesen werden.");
    if (!antwort) return;
    setVorschau(antwort);
    setOptionen((alt) => ({ ...alt, zuordnung: antwort.vorgeschlagene_zuordnung, dezimal: antwort.dezimal_vorschlag, blatt: antwort.blatt }));
    setSchritt("zuordnung");
  }

  async function pruefen() {
    if (!datei) return;
    const antwort = await ausfuehren(() => pruefeImport(accessToken, ziel, datei, { ...optionen, fehlerhafte_auslassen: false }), "Die Prüfung ist fehlgeschlagen.");
    if (!antwort) return;
    setBericht(antwort);
    setOptionen((alt) => ({ ...alt, fehlerhafte_auslassen: false }));
    setSchritt("bericht");
  }

  async function uebernehmen() {
    if (!datei) return;
    const antwort = await ausfuehren(() => importiere(accessToken, ziel, datei, optionen), "Der Import ist fehlgeschlagen.");
    if (!antwort) return;
    setErgebnis(antwort);
    setSchritt("fertig");
  }

  async function zuruecknehmen() {
    if (!ergebnis) return;
    const antwort = await ausfuehren(() => macheImportRueckgaengig(accessToken, ergebnis.import_id), "Rückgängig machen ist fehlgeschlagen.");
    if (!antwort) return;
    setRueckgaengig(
      antwort.behalten > 0
        ? `${antwort.geloescht} entfernt. ${antwort.behalten} bleiben, weil sie schon verwendet werden.`
        : `${antwort.geloescht} entfernt. Der Import ist rückgängig gemacht.`,
    );
  }

  function zuordnen(feld: string, spalte: string) {
    setOptionen((alt) => {
      const zuordnung = { ...alt.zuordnung };
      // Eine Spalte gehoert genau einem Feld: eine bisherige Zuordnung derselben Spalte wird geloest.
      for (const [schluessel, wert] of Object.entries(zuordnung)) if (wert === spalte) delete zuordnung[schluessel];
      if (spalte) zuordnung[feld] = spalte;
      else delete zuordnung[feld];
      return { ...alt, zuordnung };
    });
  }

  async function vorlageLaden(format: "csv" | "xlsx") {
    const inhalt = await ausfuehren(() => ladeVorlage(accessToken, ziel, format), "Die Vorlage konnte nicht geladen werden.");
    if (inhalt) downloadBlob(inhalt, `bilantiq-vorlage-${ziel}.${format}`);
  }

  async function fehlerlisteLaden() {
    if (!datei) return;
    const inhalt = await ausfuehren(() => ladeFehlerliste(accessToken, ziel, datei, optionen), "Die Fehlerliste konnte nicht erstellt werden.");
    if (inhalt) downloadBlob(inhalt, `fehlerliste-${ziel}.csv`);
  }

  const zuImportieren = bericht ? bericht.neu + bericht.ergaenzen : 0;
  const zugeordnet = (...felder: string[]) => felder.some((feld) => optionen.zuordnung[feld]);
  const pflichtFehlt = !vorschau
    || (ziel === "kontakte" && !zugeordnet("name", "vorname", "nachname"))
    || (ziel === "produkte" && !zugeordnet("bezeichnung"))
    || (ziel === "rechnungen" && !(
      zugeordnet("rechnungsnummer") && zugeordnet("rechnungsdatum") && zugeordnet("kunde", "kundennummer")
      && zugeordnet("brutto", "netto", "netto_19", "netto_7", "netto_0")
    ));

  return (
    <section className="panel import-assistent" aria-labelledby="import-titel">
      <div className="import-kopf">
        <h2 id="import-titel">{begriffe.titel}</h2>
        <ol className="import-schritte" aria-label="Fortschritt">
          {(["datei", "zuordnung", "bericht", "fertig"] as Schritt[]).map((name, index) => (
            <li key={name} aria-current={schritt === name ? "step" : undefined} className={schritt === name ? "aktiv" : undefined}>
              {index + 1}. {{ datei: "Datei", zuordnung: "Spalten", bericht: "Prüfen", fertig: "Fertig" }[name]}
            </li>
          ))}
        </ol>
      </div>

      {fehler && <p className="auth-error" role="alert">{fehler}</p>}

      {schritt === "datei" && (
        <>
          <p className="auth-hint">
            Lade eine CSV- oder Excel-Datei (.xlsx) hoch, zum Beispiel den Export aus deinem bisherigen Programm. Du ordnest danach
            die Spalten zu und siehst vor dem Übernehmen genau, was passiert. Es wird nichts überschrieben.
          </p>
          {ziel === "rechnungen" && (
            <p className="auth-hint">
              Die Rechnungen werden unverändert archiviert, nur Euro und keine Gutschriften. <strong>Bereits bezahlte Rechnungen zählen in keiner
              Auswertung</strong>, sie stehen ja schon in den Büchern deines alten Programms. Offene Rechnungen zählen als Forderung und gehen in
              Einnahmen und Umsatzsteuer ein, sobald du die Zahlung in Bilantiq erfasst. Bewahre den vollständigen Export aus dem alten Programm
              zusätzlich zehn Jahre auf.
            </p>
          )}
          <label className="datei-ziel">
            <input
              ref={inputRef} type="file" accept=".csv,.txt,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={laedt} onChange={(e) => { const f = e.target.files?.[0]; if (f) void dateiGewaehlt(f); }}
            />
            <span>{laedt ? "Wird gelesen …" : "Datei auswählen"}</span>
          </label>
          <p className="auth-hint">
            Noch keine Datei? Lade die Vorlage als{" "}
            <button type="button" className="auth-link inline" onClick={() => vorlageLaden("xlsx")}>Excel</button> oder{" "}
            <button type="button" className="auth-link inline" onClick={() => vorlageLaden("csv")}>CSV</button> herunter.
          </p>
          <div className="actions">
            <button type="button" className="auth-link" onClick={onAbbrechen}>Abbrechen</button>
          </div>
        </>
      )}

      {schritt === "zuordnung" && vorschau && (
        <>
          <p className="auth-hint">
            <strong>{vorschau.anzahl_zeilen} Zeilen</strong> in „{datei?.name}“
            {vorschau.format === "csv" ? ` (Kodierung ${vorschau.kodierung}, Trennzeichen „${vorschau.trennzeichen === "\t" ? "Tab" : vorschau.trennzeichen}“)` : ""}.
            Bitte prüfe, welche Spalte in welches Feld gehört. Vorschläge sind schon eingetragen.
          </p>
          {vorschau.blaetter.length > 1 && datei && (
            <div className="field-row">
              <div>
                <label htmlFor="import-blatt">Tabellenblatt</label>
                <select id="import-blatt" value={vorschau.blatt ?? ""} onChange={(e) => void dateiGewaehlt(datei, e.target.value)}>
                  {vorschau.blaetter.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </div>
            </div>
          )}
          <div className="zuordnung-raster">
            {vorschau.felder.map((feld) => {
              const spalte = optionen.zuordnung[feld.schluessel];
              return (
                <div key={feld.schluessel} className="zuordnung-feld">
                  <label htmlFor={`zu-${feld.schluessel}`}>{feld.label}{feld.pflicht ? " *" : ""}</label>
                  <select id={`zu-${feld.schluessel}`} value={spalte ?? ""} onChange={(e) => zuordnen(feld.schluessel, e.target.value)}>
                    <option value="">nicht übernehmen</option>
                    {vorschau.kopfzeilen.map((kopf) => <option key={kopf} value={kopf}>{kopf}</option>)}
                  </select>
                  <span className="zuordnung-beispiel">{spalte ? beispielWert(vorschau, spalte) || "leer in den ersten Zeilen" : " "}</span>
                </div>
              );
            })}
          </div>
          {ziel === "rechnungen" && (
            <p className="auth-hint">
              * Betrag: entweder Brutto, oder Netto mit USt, oder Netto je Steuersatz (19 %, 7 %, 0 %). Bei gemischten Steuersätzen
              ohne diese Aufteilung kann Bilantiq den Steuersatz nicht erkennen und lehnt die Zeile ab. Den offenen Betrag, „bezahlt am“ oder
              den Status brauchst du, damit bezahlte Rechnungen nicht als offen gelten.
            </p>
          )}
          {ziel === "kontakte" && (
            <p className="auth-hint">* Name genügt, alternativ Vor- und Nachname. Ohne Firmenname wird der Kontakt als Privatkunde angelegt.</p>
          )}

          <div className="field-row">
            <div>
              <label htmlFor="import-dezimal">Zahlenformat</label>
              <select id="import-dezimal" value={optionen.dezimal} onChange={(e) => setOptionen({ ...optionen, dezimal: e.target.value as ImportOptionen["dezimal"] })}>
                <option value="komma">1.234,56 (deutsch)</option>
                <option value="punkt">1,234.56 (englisch)</option>
              </select>
            </div>
            {ziel === "rechnungen" && (
              <>
                <div>
                  <label htmlFor="import-zahlungsziel">Fälligkeit, wenn die Datei keine hat</label>
                  <select
                    id="import-zahlungsziel" value={optionen.zahlungsziel_tage ?? 14}
                    onChange={(e) => setOptionen({ ...optionen, zahlungsziel_tage: Number(e.target.value) })}
                  >
                    {[7, 14, 30, 60].map((tage) => <option key={tage} value={tage}>Rechnungsdatum + {tage} Tage</option>)}
                  </select>
                </div>
                <div>
                  <label className="checkbox-row">
                    <input
                      type="checkbox" checked={optionen.fehlende_kunden_anlegen ?? false}
                      onChange={(e) => setOptionen({ ...optionen, fehlende_kunden_anlegen: e.target.checked })}
                    />
                    Fehlende Kunden als Kontakte anlegen
                  </label>
                </div>
              </>
            )}
            {ziel === "produkte" && (
              <div>
                <label htmlFor="import-ust">USt-Satz, wenn keiner angegeben ist</label>
                <select id="import-ust" value={optionen.standard_ust_satz} onChange={(e) => setOptionen({ ...optionen, standard_ust_satz: e.target.value })}>
                  <option value="19">19 %</option>
                  <option value="7">7 %</option>
                  <option value="0">0 %</option>
                </select>
              </div>
            )}
            {ziel !== "rechnungen" && (
              <div>
                <label htmlFor="import-doppelte">Wenn schon vorhanden</label>
                <select id="import-doppelte" value={optionen.doppelte} onChange={(e) => setOptionen({ ...optionen, doppelte: e.target.value as ImportOptionen["doppelte"] })}>
                  <option value="ueberspringen">überspringen</option>
                  <option value="ergaenzen">leere Felder ergänzen</option>
                </select>
              </div>
            )}
          </div>

          <div className="actions">
            <button type="button" className="button-primary" onClick={pruefen} disabled={laedt || pflichtFehlt}>
              {laedt ? "Wird geprüft …" : "Prüfen"}
            </button>
            <button type="button" className="auth-link" onClick={() => { setSchritt("datei"); setVorschau(null); if (inputRef.current) inputRef.current.value = ""; }}>
              Andere Datei
            </button>
            <button type="button" className="auth-link" onClick={onAbbrechen}>Abbrechen</button>
          </div>
        </>
      )}

      {schritt === "bericht" && bericht && (
        <>
          <p className="auth-hint">Probelauf: Es wurde noch nichts gespeichert.</p>
          <div className="import-zaehler">
            <div><strong>{bericht.neu}</strong><span>neu</span></div>
            {bericht.ergaenzen > 0 && <div><strong>{bericht.ergaenzen}</strong><span>werden ergänzt</span></div>}
            <div><strong>{bericht.vorhanden}</strong><span>schon vorhanden</span></div>
            {bericht.doppelt > 0 && <div><strong>{bericht.doppelt}</strong><span>doppelt in der Datei</span></div>}
            <div className={bericht.fehler > 0 ? "import-zaehler--fehler" : undefined}><strong>{bericht.fehler}</strong><span>mit Fehlern</span></div>
          </div>

          {bericht.beispiele.length > 0 && (
            <>
              <h3 className="import-unterkopf">So werden die ersten {begriffe.mehrzahl} angelegt</h3>
              <div className="table-scroll">
                <table className="positions-table">
                  <thead><tr>{Object.keys(bericht.beispiele[0]).map((label) => <th key={label}>{label}</th>)}</tr></thead>
                  <tbody>
                    {bericht.beispiele.map((beispiel, index) => (
                      <tr key={index}>{Object.keys(bericht.beispiele[0]).map((label) => <td key={label}>{beispiel[label] ?? ""}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {bericht.zeilen.length > 0 && (
            <>
              <h3 className="import-unterkopf">Hinweise je Zeile</h3>
              <div className="table-scroll">
                <table className="positions-table">
                  <thead><tr><th>Zeile</th><th>{begriffe.einzahl}</th><th>Ergebnis</th><th>Details</th></tr></thead>
                  <tbody>
                    {bericht.zeilen.map((zeile) => (
                      <tr key={zeile.nummer} className={zeile.status === "fehler" ? "zeile--fehler" : undefined}>
                        <td>{zeile.nummer}</td>
                        <td>{zeile.anzeige || "—"}</td>
                        <td>{STATUS_LABEL[zeile.status]}</td>
                        <td>
                          {[...zeile.fehler, ...zeile.hinweise, zeile.grund ? `Erkannt an: ${zeile.grund}` : "", zeile.ergaenzt.length ? `Ergänzt: ${zeile.ergaenzt.join(", ")}` : ""]
                            .filter(Boolean)
                            .map((text, index) => <div key={index}>{text}</div>)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {bericht.fehler > 0 && (
            <div className="import-fehlerbox">
              <p>
                {bericht.fehler} Zeilen können so nicht übernommen werden. Lade die Fehlerliste herunter, korrigiere sie und lade sie
                danach erneut hoch, oder übernimm nur die fehlerfreien Zeilen.
              </p>
              <button type="button" className="auth-link" onClick={fehlerlisteLaden} disabled={laedt}>Fehlerliste herunterladen</button>
              <label className="checkbox-row">
                <input type="checkbox" checked={optionen.fehlerhafte_auslassen} onChange={(e) => setOptionen({ ...optionen, fehlerhafte_auslassen: e.target.checked })} />
                Ohne die {bericht.fehler} fehlerhaften Zeilen importieren
              </label>
            </div>
          )}

          <div className="actions">
            <button
              type="button" className="button-primary" onClick={uebernehmen}
              disabled={laedt || zuImportieren === 0 || (bericht.fehler > 0 && !optionen.fehlerhafte_auslassen)}
            >
              {laedt ? "Wird übernommen …" : zuImportieren === 0 ? "Nichts zu übernehmen" : `${zuImportieren} ${zuImportieren === 1 ? begriffe.einzahl : begriffe.mehrzahl} übernehmen`}
            </button>
            <button type="button" className="auth-link" onClick={() => setSchritt("zuordnung")}>Zuordnung ändern</button>
            <button type="button" className="auth-link" onClick={onAbbrechen}>Abbrechen</button>
          </div>
        </>
      )}

      {schritt === "fertig" && ergebnis && (
        <>
          <p className="import-erfolg" role="status">
            {ergebnis.neu} {ergebnis.neu === 1 ? begriffe.einzahl : begriffe.mehrzahl} angelegt
            {ergebnis.ergaenzen > 0 ? `, ${ergebnis.ergaenzen} ergänzt` : ""}
            {ergebnis.vorhanden + ergebnis.doppelt > 0 ? `, ${ergebnis.vorhanden + ergebnis.doppelt} übersprungen` : ""}.
          </p>
          {rueckgaengig && <p className="auth-hint" role="status">{rueckgaengig}</p>}
          <div className="actions">
            <button type="button" className="button-primary" onClick={onFertig}>Fertig</button>
            {!rueckgaengig && (
              <button type="button" className="auth-link" onClick={zuruecknehmen} disabled={laedt}>Import rückgängig machen</button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
