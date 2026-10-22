import { useEffect, useState } from "react";
import { ApiError } from "../auth/api";
import { PageHeader } from "../../components/PageHeader";
import { formatMoney } from "../../lib/format";
import { getCashflow, type Cashflow } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

function formatWoche(start: string, ende: string): string {
  const s = new Date(start);
  const e = new Date(ende);
  const fmt = (d: Date) => d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
  return `${fmt(s)}–${fmt(e)}`;
}

export function CashflowPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [cashflow, setCashflow] = useState<Cashflow | null>(null);

  useEffect(() => {
    getCashflow(accessToken)
      .then((result) => { setCashflow(result); setStatus("ready"); })
      .catch((err) => { setError(err instanceof ApiError ? err.message : "Prognose konnte nicht geladen werden."); setStatus("error"); });
  }, [accessToken]);

  return (
    <div className="invoices-page">
      <PageHeader title="Cashflow-Prognose" description="Deterministische Vorschau auf fällige Rechnungen und typische Ausgaben." onBack={onBack} />

      {status === "loading" && <div className="panel"><p>Wird berechnet …</p></div>}
      {status === "error" && <div className="panel"><p className="auth-error" role="alert">{error}</p></div>}

      {status === "ready" && cashflow && (
        <>
          {cashflow.warnung && (
            <div className="panel" style={{ borderColor: "var(--danger)" }}>
              <p className="auth-error" role="alert">{cashflow.warnung}</p>
            </div>
          )}

          {Number(cashflow.ueberfaellige_rechnungen_betrag) > 0 && (
            <div className="panel">
              <p className="hinweis">
                {cashflow.ueberfaellige_rechnungen_anzahl} ueberfaellige Rechnung(en) im Wert von{" "}
                {formatMoney(cashflow.ueberfaellige_rechnungen_betrag)} sind nicht in der Prognose enthalten — ihr
                Zahlungseingang ist bereits unsicher.
              </p>
            </div>
          )}

          <div className="panel">
            <div className="table-scroll">
            <table className="positions-table">
              <thead>
                <tr>
                  <th>Woche</th><th>Erwarteter Zufluss</th><th>Rechnungen</th>
                  <th>Geschaetzter Abfluss</th><th>Veraenderung</th><th>Kumuliert</th>
                </tr>
              </thead>
              <tbody>
                {cashflow.wochen.map((w) => (
                  <tr key={w.woche_start}>
                    <td>{formatWoche(w.woche_start, w.woche_ende)}</td>
                    <td className="number">{formatMoney(w.erwarteter_zufluss)}</td>
                    <td>{w.anzahl_faellige_rechnungen}</td>
                    <td className="number">−{formatMoney(w.geschaetzter_abfluss)}</td>
                    <td style={{ color: Number(w.saldo_veraenderung) < 0 ? "var(--danger)" : "var(--accent-ink)" }}>
                      {Number(w.saldo_veraenderung) >= 0 ? "+" : ""}{formatMoney(w.saldo_veraenderung)}
                    </td>
                    <td style={{ color: Number(w.kumulierter_saldo) < 0 ? "var(--danger)" : "inherit" }}>
                      {formatMoney(w.kumulierter_saldo)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="hinweis" style={{ marginTop: 16 }}>{cashflow.hinweis}</p>
          </div>
        </>
      )}
    </div>
  );
}
