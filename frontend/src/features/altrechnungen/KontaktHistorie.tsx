import { useState } from "react";
import { StatusPill } from "../../components/StatusPill";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { ladeHistorie, type Historie } from "./api";

/** Alle Rechnungen eines Kontakts (aus Bilantiq und aus dem alten Programm) mit Umsatz. Wird erst beim
 * Aufklappen geladen, damit das Bearbeiten eines Kontakts nicht auf die Historie wartet. */
export function KontaktHistorie({ accessToken, kontaktId }: { accessToken: string; kontaktId: string }) {
  const [historie, setHistorie] = useState<Historie | null>(null);
  const [fehler, setFehler] = useState("");

  async function laden() {
    if (historie) return;
    try {
      setHistorie(await ladeHistorie(accessToken, kontaktId));
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Die Historie konnte nicht geladen werden.");
    }
  }

  return (
    <details className="formular-abschnitt" onToggle={(e) => { if ((e.currentTarget as HTMLDetailsElement).open) void laden(); }}>
      <summary>Rechnungshistorie</summary>
      {fehler && <p className="auth-error" role="alert">{fehler}</p>}
      {!historie && !fehler && <p className="auth-hint">Wird geladen …</p>}
      {historie && historie.eintraege.length === 0 && <p className="auth-hint">Für diesen Kontakt gibt es noch keine Rechnungen.</p>}
      {historie && historie.eintraege.length > 0 && (
        <>
          <p className="auth-hint">
            Umsatz brutto: <strong>{formatMoney(historie.umsatz_brutto_bilantiq)}</strong> aus Bilantiq
            {Number(historie.umsatz_brutto_altsystem) > 0 && <> und <strong>{formatMoney(historie.umsatz_brutto_altsystem)}</strong> aus dem alten Programm</>}.
            {" "}Noch offen: <strong>{formatMoney(historie.offen_brutto)}</strong>.
          </p>
          <div className="table-scroll">
            <table className="positions-table">
              <thead><tr><th>Nummer</th><th>Datum</th><th>Quelle</th><th className="number">Brutto</th><th className="number">Offen</th><th>Status</th></tr></thead>
              <tbody>
                {historie.eintraege.map((e) => (
                  <tr key={`${e.art}-${e.id}`}>
                    <td>{e.nummer ?? "Entwurf"}</td>
                    <td>{formatDate(e.datum)}</td>
                    <td>{e.art === "altsystem" ? "Altes Programm" : "Bilantiq"}</td>
                    <td className="number">{formatMoney(e.brutto)}</td>
                    <td className="number">{Number(e.offen) > 0 ? formatMoney(e.offen) : "—"}</td>
                    <td><StatusPill status={e.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </details>
  );
}
