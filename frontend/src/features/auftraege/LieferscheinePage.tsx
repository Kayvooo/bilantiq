import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { CheckIcon } from "../../components/icons";
import { ApiError } from "../auth/api";
import { downloadBlob } from "../invoices/downloadBlob";
import { formatDate } from "../../lib/format";
import {
  createLieferschein,
  downloadLieferscheinPdf,
  listAuftragsbestaetigungen,
  listLieferscheine,
  type Auftragsbestaetigung,
  type Lieferschein,
  type LieferscheinPositionDraft,
} from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

const LEER_POSITION: LieferscheinPositionDraft = { beschreibung: "", menge: "1" };

function heute(): string {
  return new Date().toISOString().slice(0, 10);
}

export function LieferscheinePage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [bestaetigungen, setBestaetigungen] = useState<Auftragsbestaetigung[]>([]);
  const [lieferscheine, setLieferscheine] = useState<Lieferschein[]>([]);
  const [ausgewaehlteAbId, setAusgewaehlteAbId] = useState("");
  const [lieferdatum, setLieferdatum] = useState(heute());
  const [positionen, setPositionen] = useState<LieferscheinPositionDraft[]>([{ ...LEER_POSITION }]);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function reload() {
    try {
      const [ab, ls] = await Promise.all([listAuftragsbestaetigungen(accessToken), listLieferscheine(accessToken)]);
      setBestaetigungen(ab);
      setLieferscheine(ls);
      if (!ausgewaehlteAbId && ab.length > 0) setAusgewaehlteAbId(ab[0].id);
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

  if (status === "loading") return <PageState label="Lieferscheine werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={reload} />;

  function updatePosition(index: number, field: keyof LieferscheinPositionDraft, value: string) {
    setPositionen((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!ausgewaehlteAbId) return;
    setCreating(true);
    setError("");
    try {
      await createLieferschein(accessToken, { auftragsbestaetigung_id: ausgewaehlteAbId, lieferdatum, positionen });
      setPositionen([{ ...LEER_POSITION }]);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lieferschein konnte nicht erstellt werden.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDownload(ls: Lieferschein) {
    setBusyId(ls.id);
    try {
      const blob = await downloadLieferscheinPdf(accessToken, ls.id);
      downloadBlob(blob, `${ls.nummer}.pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "PDF konnte nicht geladen werden.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="invoices-page">
      <PageHeader
        title="Lieferscheine"
        description="Lieferungen zu einer Auftragsbestätigung dokumentieren — ohne Preise."
        onBack={onBack}
      />

      <form className="panel" onSubmit={handleSubmit}>
        <h2>Neuer Lieferschein</h2>
        {bestaetigungen.length === 0 ? (
          <p className="auth-hint">Noch keine Auftragsbestätigung vorhanden. Lege zuerst eine an.</p>
        ) : (
          <>
            <label htmlFor="ls-ab">Auftragsbestätigung</label>
            <select id="ls-ab" value={ausgewaehlteAbId} onChange={(e) => setAusgewaehlteAbId(e.target.value)} required>
              {bestaetigungen.map((ab) => (<option key={ab.id} value={ab.id}>{ab.nummer}</option>))}
            </select>

            <label htmlFor="ls-datum">Lieferdatum</label>
            <input id="ls-datum" type="date" value={lieferdatum} onChange={(e) => setLieferdatum(e.target.value)} required />

            <div className="table-scroll">
              <table className="positions-table">
                <thead><tr><th>Beschreibung</th><th>Menge</th></tr></thead>
                <tbody>
                  {positionen.map((p, i) => (
                    <tr key={i}>
                      <td><input value={p.beschreibung} onChange={(e) => updatePosition(i, "beschreibung", e.target.value)} required /></td>
                      <td><input value={p.menge} onChange={(e) => updatePosition(i, "menge", e.target.value)} required /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button type="button" className="auth-link" onClick={() => setPositionen((prev) => [...prev, { ...LEER_POSITION }])}>
              + Position
            </button>

            {error && <p className="auth-error" role="alert">{error}</p>}
            <button type="submit" disabled={creating}>{creating ? "Wird erstellt …" : "Lieferschein erstellen"}</button>
          </>
        )}
      </form>

      <h2 className="section-title">Alle Lieferscheine</h2>
      {lieferscheine.length === 0 ? (
        <div className="empty-state">
          <h2>Noch kein Lieferschein erstellt</h2>
          <ul>
            <li><CheckIcon width={18} height={18} /> Ohne Preise — genau wie im Handel üblich</li>
            <li><CheckIcon width={18} height={18} /> Mehrere Lieferscheine je Auftragsbestätigung möglich (Teillieferungen)</li>
          </ul>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Nummer</th><th>Lieferdatum</th><th>Aktionen</th></tr></thead>
            <tbody>
              {lieferscheine.map((ls) => (
                <tr key={ls.id}>
                  <td>{ls.nummer}</td>
                  <td>{formatDate(ls.lieferdatum)}</td>
                  <td className="invoice-actions">
                    <button type="button" className="auth-link" disabled={busyId === ls.id} onClick={() => handleDownload(ls)}>
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
