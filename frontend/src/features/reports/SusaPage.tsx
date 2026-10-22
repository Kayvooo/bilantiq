import { useEffect, useState } from "react";
import { ComplianceHinweis } from "../../components/ComplianceHinweis";
import { PageHeader } from "../../components/PageHeader";
import { ApiError } from "../auth/api";
import { formatMoney } from "../../lib/format";
import { getSusa, type Susa } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

export function SusaPage({ accessToken, onBack }: Props) {
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [susa, setSusa] = useState<Susa | null>(null);

  useEffect(() => {
    getSusa(accessToken, jahr)
      .then((result) => { setSusa(result); setStatus("ready"); })
      .catch((err) => { setError(err instanceof ApiError ? err.message : "SuSa konnte nicht geladen werden."); setStatus("error"); });
  }, [accessToken, jahr]);

  return (
    <div className="invoices-page">
      <PageHeader title="Summen- und Saldenliste" description="Soll, Haben und Saldo je Konto für die Steuerkanzlei." onBack={onBack} />

      <ComplianceHinweis titel="SKR03-Konten: nicht steuerberatergeprüft">
        Die verwendeten SKR03-Kontonummern sind eine Annahme und wurden nicht mit einem
        Steuerberater abgestimmt. Vor der Übergabe an die Kanzlei bitte bestätigen lassen.
      </ComplianceHinweis>

      <div className="panel">
        <label htmlFor="susa-jahr">Jahr</label>
        <select id="susa-jahr" value={jahr} onChange={(e) => setJahr(Number(e.target.value))}>
          {[jahr + 1, jahr, jahr - 1, jahr - 2].map((j) => (<option key={j} value={j}>{j}</option>))}
        </select>
      </div>

      {status === "loading" && <div className="panel"><p>Wird berechnet …</p></div>}
      {status === "error" && <div className="panel"><p className="auth-error" role="alert">{error}</p></div>}

      {status === "ready" && susa && (
        susa.konten.length === 0 ? (
          <div className="empty-state">
            <h2>Noch keine Buchungen {jahr}</h2>
            <p className="auth-hint" style={{ margin: 0 }}>Bezahlte Rechnungen und gebuchte Ausgaben erscheinen hier.</p>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table className="positions-table">
                <thead>
                  <tr><th>Konto</th><th>Bezeichnung</th><th className="number">Soll</th><th className="number">Haben</th><th className="number">Saldo</th></tr>
                </thead>
                <tbody>
                  {susa.konten.map((konto) => (
                    <tr key={konto.konto}>
                      <td>{konto.konto}</td>
                      <td>{konto.bezeichnung}</td>
                      <td className="number">{formatMoney(konto.soll)}</td>
                      <td className="number">{formatMoney(konto.haben)}</td>
                      <td className="number">{formatMoney(konto.saldo)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}><strong>Summe</strong></td>
                    <td className="number"><strong>{formatMoney(susa.summe_soll)}</strong></td>
                    <td className="number"><strong>{formatMoney(susa.summe_haben)}</strong></td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
            <p className="hinweis">{susa.hinweis}</p>
          </>
        )
      )}
    </div>
  );
}
