import { useEffect, useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { downloadBlob } from "./downloadBlob";
import { downloadInvoicePdf, listInvoices, type Invoice } from "./api";

interface Props { accessToken: string; onBack: () => void }

export function GutschriftenPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    setStatus("loading");
    setError("");
    try {
      setInvoices(await listInvoices(accessToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gutschriften konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleDownload(invoice: Invoice) {
    setBusyId(invoice.id);
    setError("");
    try {
      downloadBlob(await downloadInvoicePdf(accessToken, invoice.id), `${invoice.nummer ?? invoice.id}.pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "PDF konnte nicht erstellt werden.");
    } finally {
      setBusyId(null);
    }
  }

  if (status === "loading") return <PageState label="Gutschriften werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={load} />;

  const nummerById = new Map(invoices.map((i) => [i.id, i.nummer]));
  const gutschriften = invoices.filter((i) => i.korrigiert_invoice_id !== null);

  return (
    <div className="invoices-page">
      <PageHeader
        title="Gutschriften"
        description="Storno-Korrekturrechnungen mit negativem Betrag zu einer ursprünglichen Rechnung."
        onBack={onBack}
      />

      {error && <p className="auth-error" role="alert">{error}</p>}

      <p className="hinweis">
        Eine Gutschrift entsteht hier immer beim Stornieren einer finalen Rechnung (in Rechnungen → „Stornieren"),
        nicht als eigenständiges Dokument — es gibt aktuell keine Möglichkeit, eine Gutschrift ohne Bezug zu
        einer bestehenden Rechnung auszustellen.
      </p>

      {gutschriften.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Gutschriften</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Storniere eine finale Rechnung, um hier eine Gutschrift zu sehen.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Nummer</th><th>Zu Rechnung</th><th className="number">Betrag</th><th /></tr></thead>
            <tbody>
              {gutschriften.map((invoice) => (
                <tr key={invoice.id}>
                  <td>{invoice.nummer}</td>
                  <td>{invoice.korrigiert_invoice_id ? nummerById.get(invoice.korrigiert_invoice_id) ?? "—" : "—"}</td>
                  <td className="number">{formatMoney(invoice.brutto_gesamt)}</td>
                  <td>
                    <button type="button" className="auth-link" disabled={busyId === invoice.id} onClick={() => handleDownload(invoice)}>
                      {busyId === invoice.id ? "Wird erstellt …" : "PDF"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
