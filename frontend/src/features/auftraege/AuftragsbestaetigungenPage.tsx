import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { CheckIcon } from "../../components/icons";
import { ApiError } from "../auth/api";
import { downloadBlob } from "../invoices/downloadBlob";
import { listQuotes, type Quote } from "../quotes/api";
import { formatDate, formatMoney } from "../../lib/format";
import {
  createAuftragsbestaetigung,
  downloadAuftragsbestaetigungPdf,
  listAuftragsbestaetigungen,
  type Auftragsbestaetigung,
} from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

export function AuftragsbestaetigungenPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [bestaetigungen, setBestaetigungen] = useState<Auftragsbestaetigung[]>([]);
  const [ausgewaehlteQuoteId, setAusgewaehlteQuoteId] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function reload() {
    try {
      const [q, ab] = await Promise.all([listQuotes(accessToken), listAuftragsbestaetigungen(accessToken)]);
      setQuotes(q);
      setBestaetigungen(ab);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Daten konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  if (status === "loading") return <PageState label="Auftragsbestätigungen werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={reload} />;

  const bestaetigteQuoteIds = new Set(bestaetigungen.map((ab) => ab.quote_id));
  const verfuegbareAngebote = quotes.filter((q) => q.status === "angenommen" && !bestaetigteQuoteIds.has(q.id));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!ausgewaehlteQuoteId) return;
    setCreating(true);
    setError("");
    try {
      await createAuftragsbestaetigung(accessToken, ausgewaehlteQuoteId);
      setAusgewaehlteQuoteId("");
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Auftragsbestätigung konnte nicht erstellt werden.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDownload(ab: Auftragsbestaetigung) {
    setBusyId(ab.id);
    try {
      const blob = await downloadAuftragsbestaetigungPdf(accessToken, ab.id);
      downloadBlob(blob, `${ab.nummer}.pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "PDF konnte nicht geladen werden.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="invoices-page">
      <PageHeader
        title="Auftragsbestätigung"
        description="Aus einem angenommenen Angebot eine feste Auftragsbestätigung erzeugen."
        onBack={onBack}
      />

      <form className="panel" onSubmit={handleSubmit}>
        <h2>Neue Auftragsbestätigung</h2>
        {verfuegbareAngebote.length === 0 ? (
          <p className="auth-hint">Kein angenommenes Angebot ohne Auftragsbestätigung vorhanden.</p>
        ) : (
          <>
            <label htmlFor="ab-quote">Angenommenes Angebot</label>
            <select id="ab-quote" value={ausgewaehlteQuoteId} onChange={(e) => setAusgewaehlteQuoteId(e.target.value)} required>
              <option value="" disabled>Bitte wählen …</option>
              {verfuegbareAngebote.map((q) => (
                <option key={q.id} value={q.id}>{q.nummer} · {formatMoney(q.brutto_gesamt, q.waehrung)}</option>
              ))}
            </select>
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button type="submit" disabled={creating || !ausgewaehlteQuoteId}>
              {creating ? "Wird erstellt …" : "Auftragsbestätigung erstellen"}
            </button>
          </>
        )}
      </form>

      <h2 className="section-title">Alle Auftragsbestätigungen</h2>
      {bestaetigungen.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Auftragsbestätigung erstellt</h2>
          <ul>
            <li><CheckIcon width={18} height={18} /> Positionen und Summen werden fest aus dem Angebot übernommen</li>
            <li><CheckIcon width={18} height={18} /> Grundlage für spätere Lieferscheine</li>
          </ul>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Nummer</th><th>Erstellt am</th><th>Betrag</th><th>Aktionen</th></tr></thead>
            <tbody>
              {bestaetigungen.map((ab) => (
                <tr key={ab.id}>
                  <td>{ab.nummer}</td>
                  <td>{formatDate(ab.erstellt_am.slice(0, 10))}</td>
                  <td className="number">{formatMoney(ab.brutto_gesamt, ab.waehrung)}</td>
                  <td className="invoice-actions">
                    <button type="button" className="auth-link" disabled={busyId === ab.id} onClick={() => handleDownload(ab)}>
                      PDF
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
