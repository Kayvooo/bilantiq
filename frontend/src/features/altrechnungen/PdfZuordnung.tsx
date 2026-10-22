import { useRef, useState } from "react";
import { ApiError } from "../auth/api";
import { ladePdfsHoch, ordnePdfZu, type Altrechnung, type PdfErgebnis } from "./api";

interface Zeile {
  datei: File;
  ergebnis: PdfErgebnis;
}

const MAX_JE_ANFRAGE = 20;

/** PDFs der Altrechnungen ablegen: mehrere Dateien auf einmal, Zuordnung ueber die Rechnungsnummer im Dateinamen.
 * Was sich nicht eindeutig zuordnen laesst, wird mit Grund gezeigt und kann von Hand zugeordnet werden. Abgelegte
 * PDFs sind unveraenderbar, es gibt kein Loeschen und kein Ersetzen. */
export function PdfZuordnung({ accessToken, ohnePdf, onGeaendert }: { accessToken: string; ohnePdf: Altrechnung[]; onGeaendert: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [zeilen, setZeilen] = useState<Zeile[]>([]);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState("");
  const [wahl, setWahl] = useState<Record<number, string>>({});
  const [auf, setAuf] = useState(false);

  function meldeFehler(err: unknown, standard: string) {
    setFehler(err instanceof ApiError ? err.message : standard);
  }

  async function hochladen(dateien: File[]) {
    setLaedt(true);
    setFehler("");
    setWahl({});
    try {
      const gesammelt: Zeile[] = [];
      for (let start = 0; start < dateien.length; start += MAX_JE_ANFRAGE) {
        const stapel = dateien.slice(start, start + MAX_JE_ANFRAGE);
        const antwort = await ladePdfsHoch(accessToken, stapel);
        antwort.ergebnisse.forEach((ergebnis, index) => gesammelt.push({ datei: stapel[index], ergebnis }));
      }
      setZeilen(gesammelt);
      if (gesammelt.some((z) => z.ergebnis.status === "zugeordnet")) onGeaendert();
    } catch (err) {
      meldeFehler(err, "Die PDFs konnten nicht abgelegt werden.");
    } finally {
      setLaedt(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function vonHandZuordnen(index: number) {
    const id = wahl[index];
    if (!id) return;
    setLaedt(true);
    setFehler("");
    try {
      const rechnung = await ordnePdfZu(accessToken, id, zeilen[index].datei);
      setZeilen((alt) => alt.map((z, i) => (i === index
        ? { ...z, ergebnis: { ...z.ergebnis, status: "zugeordnet", altrechnung_id: rechnung.id, nummer: rechnung.nummer, grund: null } }
        : z)));
      onGeaendert();
    } catch (err) {
      meldeFehler(err, "Das PDF konnte nicht zugeordnet werden.");
    } finally {
      setLaedt(false);
    }
  }

  const zugeordnet = zeilen.filter((z) => z.ergebnis.status === "zugeordnet").length;
  const offen = zeilen.filter((z) => z.ergebnis.status !== "zugeordnet");
  // Eine Rechnung, die in dieser Runde schon ein PDF bekam, taucht nicht mehr zur Auswahl auf.
  const bekommenHaben = new Set(zeilen.filter((z) => z.ergebnis.status === "zugeordnet").map((z) => z.ergebnis.altrechnung_id));
  const auswahl = ohnePdf.filter((a) => !bekommenHaben.has(a.id));

  return (
    <details className="panel pdf-archiv" open={auf} onToggle={(e) => setAuf((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        <h3 id="pdf-titel">PDFs der alten Rechnungen ablegen{ohnePdf.length > 0 ? ` (${ohnePdf.length} ohne PDF)` : ""}</h3>
      </summary>
      <p className="auth-hint">
        Wähle mehrere PDFs auf einmal. Bilantiq ordnet sie über die Rechnungsnummer im Dateinamen zu (zum Beispiel „RE-2024-0001.pdf“).
        Abgelegte PDFs werden verschlüsselt gespeichert und bleiben unverändert, sie lassen sich nicht löschen oder ersetzen.
      </p>
      <label className="datei-ziel">
        <input
          ref={inputRef} type="file" accept="application/pdf,.pdf" multiple disabled={laedt}
          onChange={(e) => { const dateien = Array.from(e.target.files ?? []); if (dateien.length) void hochladen(dateien); }}
        />
        <span>{laedt ? "Wird abgelegt …" : "PDFs auswählen"}</span>
      </label>
      {fehler && <p className="auth-error" role="alert">{fehler}</p>}

      {zeilen.length > 0 && (
        <>
          <p className="import-erfolg" role="status">
            {zugeordnet} von {zeilen.length} {zeilen.length === 1 ? "PDF" : "PDFs"} zugeordnet.
            {offen.length > 0 ? ` ${offen.length} brauchen noch einen Blick.` : ""}
          </p>
          {offen.length > 0 && (
            <div className="table-scroll">
              <table className="positions-table">
                <thead><tr><th>Datei</th><th>Ergebnis</th><th>Rechnung zuordnen</th></tr></thead>
                <tbody>
                  {zeilen.map((zeile, index) => zeile.ergebnis.status === "zugeordnet" ? null : (
                    <tr key={`${zeile.ergebnis.dateiname}-${index}`}>
                      <td>{zeile.ergebnis.dateiname}</td>
                      <td>{zeile.ergebnis.grund}</td>
                      <td>
                        {zeile.ergebnis.status === "abgelehnt" ? "—" : (
                          <div className="actions">
                            <select aria-label={`Rechnung für ${zeile.ergebnis.dateiname}`} value={wahl[index] ?? ""} onChange={(e) => setWahl({ ...wahl, [index]: e.target.value })}>
                              <option value="">Rechnung wählen …</option>
                              {auswahl.map((a) => <option key={a.id} value={a.id}>{a.nummer}, {a.kontakt_name}</option>)}
                            </select>
                            <button type="button" disabled={laedt || !wahl[index]} onClick={() => void vonHandZuordnen(index)}>Zuordnen</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </details>
  );
}
