import { useRef, useState } from "react";
import { ApiError } from "../auth/api";
import { formatDate } from "../../lib/format";
import { importiereAuszug, importVorschau, type Bankkonto, type CsvProfil, type ImportErgebnis, type ImportVorschau } from "./api";

const DATUMSFORMATE: { wert: string; label: string }[] = [
  { wert: "%d.%m.%Y", label: "TT.MM.JJJJ (31.12.2026)" },
  { wert: "%Y-%m-%d", label: "JJJJ-MM-TT (2026-12-31)" },
  { wert: "%d.%m.%y", label: "TT.MM.JJ (31.12.26)" },
  { wert: "%d/%m/%Y", label: "TT/MM/JJJJ (31/12/2026)" },
  { wert: "%m/%d/%Y", label: "MM/TT/JJJJ (12/31/2026)" },
  { wert: "%d-%m-%Y", label: "TT-MM-JJJJ (31-12-2026)" },
];

interface Props {
  accessToken: string;
  konto: Bankkonto;
  onImported: (ergebnis: ImportErgebnis) => void;
}

function SpaltenSelect({
  id, label, wert, spalten, optional, onChange,
}: { id: string; label: string; wert: string | null; spalten: string[]; optional?: boolean; onChange: (wert: string | null) => void }) {
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={wert ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        {optional && <option value="">nicht verwenden</option>}
        {!optional && wert === null && <option value="">bitte wählen</option>}
        {spalten.map((spalte) => <option key={spalte} value={spalte}>{spalte}</option>)}
      </select>
    </div>
  );
}

export function ImportPanel({ accessToken, konto, onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [datei, setDatei] = useState<File | null>(null);
  const [vorschau, setVorschau] = useState<ImportVorschau | null>(null);
  const [profil, setProfil] = useState<CsvProfil | null>(null);
  const [getrennteSpalten, setGetrennteSpalten] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  function zuruecksetzen() {
    setDatei(null);
    setVorschau(null);
    setProfil(null);
    setError("");
    setStatus("idle");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function dateiGewaehlt(event: React.ChangeEvent<HTMLInputElement>) {
    const gewaehlt = event.target.files?.[0];
    if (!gewaehlt) return;
    setDatei(gewaehlt);
    setStatus("loading");
    setError("");
    try {
      const antwort = await importVorschau(accessToken, konto.id, gewaehlt);
      setVorschau(antwort);
      const start = antwort.gespeichertes_profil ?? antwort.csv?.vorgeschlagenes_profil ?? null;
      setProfil(start);
      setGetrennteSpalten(Boolean(start && start.betrag === null && start.soll && start.haben));
      setStatus("idle");
    } catch (err) {
      setVorschau(null);
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Die Datei konnte nicht gelesen werden.");
    }
  }

  async function importieren() {
    if (!datei || !vorschau) return;
    setStatus("loading");
    setError("");
    try {
      const ergebnis = await importiereAuszug(accessToken, konto.id, datei, vorschau.format === "csv" ? profil : null);
      zuruecksetzen();
      onImported(ergebnis);
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Der Import ist fehlgeschlagen.");
    }
  }

  function aendere(teil: Partial<CsvProfil>) {
    setProfil((aktuell) => (aktuell ? { ...aktuell, ...teil } : aktuell));
  }

  const csv = vorschau?.csv ?? null;
  const spalten = csv?.kopfzeilen ?? [];
  const csvBereit = Boolean(
    profil && profil.datum && (getrennteSpalten ? profil.soll && profil.haben : profil.betrag),
  );

  return (
    <div className="panel">
      <h2>Kontoauszug importieren</h2>
      <p className="auth-hint">
        Lade den Auszug deiner Bank als CAMT.053 (XML) oder CSV hoch. Die Datei wird verschlüsselt gespeichert,
        bereits importierte Umsätze werden erkannt und nicht doppelt angelegt.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".xml,.csv,.txt,text/csv,application/xml,text/xml"
        onChange={dateiGewaehlt}
        disabled={status === "loading"}
        aria-label="Kontoauszug auswählen"
      />
      {status === "loading" && <p className="auth-hint">Wird gelesen …</p>}
      {error && <p className="auth-error" role="alert">{error}</p>}

      {vorschau?.format === "camt" && (
        <div className="bank-vorschau">
          <p>
            <strong>{vorschau.anzahl} Umsätze</strong> im CAMT.053-Auszug
            {vorschau.zeitraum_von && vorschau.zeitraum_bis && (
              <> vom {formatDate(vorschau.zeitraum_von)} bis {formatDate(vorschau.zeitraum_bis)}</>
            )}
            .
          </p>
          <button type="button" className="button-primary" onClick={importieren} disabled={status === "loading"}>Importieren</button>
          <button type="button" className="auth-link" onClick={zuruecksetzen}>Abbrechen</button>
        </div>
      )}

      {csv && profil && (
        <div className="bank-vorschau">
          <p>
            <strong>{csv.anzahl_zeilen} Zeilen</strong> gefunden (Trennzeichen „{csv.trennzeichen === "\t" ? "Tab" : csv.trennzeichen}“,
            Kodierung {csv.kodierung}).
            {vorschau?.gespeichertes_profil ? " Das zuletzt verwendete Spaltenprofil ist vorbelegt." : " Bitte prüfe die Zuordnung der Spalten."}
          </p>
          <div className="table-scroll">
            <table className="positions-table">
              <thead><tr>{csv.kopfzeilen.map((kopf) => <th key={kopf}>{kopf}</th>)}</tr></thead>
              <tbody>
                {csv.beispielzeilen.map((zeile, index) => (
                  <tr key={index}>{csv.kopfzeilen.map((kopf, spalte) => <td key={kopf}>{zeile[spalte] ?? ""}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="field-row">
            <SpaltenSelect id="bk-datum" label="Datum" wert={profil.datum || null} spalten={spalten} onChange={(wert) => aendere({ datum: wert ?? "" })} />
            <div>
              <label htmlFor="bk-datumformat">Datumsformat</label>
              <select id="bk-datumformat" value={profil.datum_format} onChange={(e) => aendere({ datum_format: e.target.value })}>
                {DATUMSFORMATE.map((format) => <option key={format.wert} value={format.wert}>{format.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="bk-dezimal">Zahlenformat</label>
              <select id="bk-dezimal" value={profil.dezimal} onChange={(e) => aendere({ dezimal: e.target.value as CsvProfil["dezimal"] })}>
                <option value="komma">1.234,56</option>
                <option value="punkt">1,234.56</option>
              </select>
            </div>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={getrennteSpalten}
              onChange={(e) => {
                setGetrennteSpalten(e.target.checked);
                aendere(e.target.checked ? { betrag: null } : { soll: null, haben: null });
              }}
            />
            Soll und Haben stehen in getrennten Spalten
          </label>
          <div className="field-row">
            {getrennteSpalten ? (
              <>
                <SpaltenSelect id="bk-soll" label="Soll (Ausgang)" wert={profil.soll} spalten={spalten} onChange={(wert) => aendere({ soll: wert })} />
                <SpaltenSelect id="bk-haben" label="Haben (Eingang)" wert={profil.haben} spalten={spalten} onChange={(wert) => aendere({ haben: wert })} />
              </>
            ) : (
              <SpaltenSelect id="bk-betrag" label="Betrag (Ausgänge negativ)" wert={profil.betrag} spalten={spalten} onChange={(wert) => aendere({ betrag: wert })} />
            )}
            <SpaltenSelect id="bk-name" label="Name der Gegenpartei" wert={profil.name} spalten={spalten} optional onChange={(wert) => aendere({ name: wert })} />
          </div>
          <div className="field-row">
            <SpaltenSelect
              id="bk-zweck" label="Verwendungszweck" wert={profil.verwendungszweck[0] ?? null} spalten={spalten} optional
              onChange={(wert) => aendere({ verwendungszweck: wert ? [wert] : [] })}
            />
            <SpaltenSelect id="bk-iban" label="IBAN der Gegenpartei" wert={profil.iban} spalten={spalten} optional onChange={(wert) => aendere({ iban: wert })} />
            <SpaltenSelect id="bk-wert" label="Wertstellung" wert={profil.wertstellung} spalten={spalten} optional onChange={(wert) => aendere({ wertstellung: wert })} />
          </div>

          <button type="button" className="button-primary" onClick={importieren} disabled={status === "loading" || !csvBereit}>Importieren</button>
          <button type="button" className="auth-link" onClick={zuruecksetzen}>Abbrechen</button>
        </div>
      )}
    </div>
  );
}
