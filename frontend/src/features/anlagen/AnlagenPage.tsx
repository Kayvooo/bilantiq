import { Fragment, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { createAnlage, getAnlagen, type AnlagenUebersicht } from "./api";

interface Props { accessToken: string; onBack: () => void }

const EMPTY_FORM = { bezeichnung: "", anschaffungsdatum: new Date().toISOString().slice(0, 10), anschaffungskosten_netto: "0.00", nutzungsdauer_jahre: "3", kategorie: "" };

export function AnlagenPage({ accessToken, onBack }: Props) {
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [uebersicht, setUebersicht] = useState<AnlagenUebersicht | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function load() {
    setStatus("loading");
    setError("");
    try {
      setUebersicht(await getAnlagen(accessToken, jahr));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anlagen konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken, jahr]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      await createAnlage(accessToken, { ...form, nutzungsdauer_jahre: Number(form.nutzungsdauer_jahre), kategorie: form.kategorie || null });
      setForm(EMPTY_FORM);
      setUebersicht(await getAnlagen(accessToken, jahr));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anlage konnte nicht angelegt werden.");
    } finally {
      setCreating(false);
    }
  }

  if (status === "loading") return <PageState label="Anlagen werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={load} />;
  if (!uebersicht) return null;

  return (
    <div className="invoices-page">
      <PageHeader title="Anlagen" description="Anlagevermögen mit linearer Abschreibung (AfA)." onBack={onBack} />

      <div className="panel">
        <label htmlFor="anl-jahr">Jahr</label>
        <select id="anl-jahr" value={jahr} onChange={(e) => setJahr(Number(e.target.value))}>
          {[jahr + 1, jahr, jahr - 1, jahr - 2].map((j) => (<option key={j} value={j}>{j}</option>))}
        </select>
      </div>

      <div className="panel dashboard-summary">
        <p className="dashboard-summary-label">AfA gesamt {uebersicht.jahr}</p>
        <p className="dashboard-summary-value">{formatMoney(uebersicht.afa_gesamt_jahr)}</p>
      </div>

      {error && <p className="auth-error" role="alert">{error}</p>}
      <p className="hinweis">{uebersicht.hinweis}</p>

      <form className="panel" onSubmit={handleCreate}>
        <h2>Neue Anlage</h2>
        <div className="field-row">
          <div>
            <label htmlFor="anl-bezeichnung">Bezeichnung</label>
            <input id="anl-bezeichnung" value={form.bezeichnung} onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })} placeholder="z.B. Laptop" required />
          </div>
          <div>
            <label htmlFor="anl-kategorie">Kategorie (optional)</label>
            <input id="anl-kategorie" value={form.kategorie} onChange={(e) => setForm({ ...form, kategorie: e.target.value })} />
          </div>
        </div>
        <div className="field-row">
          <div>
            <label htmlFor="anl-datum">Anschaffungsdatum</label>
            <input id="anl-datum" type="date" value={form.anschaffungsdatum} onChange={(e) => setForm({ ...form, anschaffungsdatum: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="anl-kosten">Anschaffungskosten (netto)</label>
            <input id="anl-kosten" value={form.anschaffungskosten_netto} onChange={(e) => setForm({ ...form, anschaffungskosten_netto: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="anl-dauer">Nutzungsdauer (Jahre)</label>
            <input id="anl-dauer" type="number" min="1" max="50" value={form.nutzungsdauer_jahre} onChange={(e) => setForm({ ...form, nutzungsdauer_jahre: e.target.value })} required />
          </div>
        </div>
        <button type="submit" disabled={creating}>{creating ? "Wird angelegt …" : "Anlage anlegen"}</button>
      </form>

      <h2 className="section-title">Alle Anlagen</h2>
      {uebersicht.anlagen.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Anlage</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Lege oben das erste Anlagegut an.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Bezeichnung</th><th>Anschaffung</th><th className="number">Kosten (netto)</th><th>Nutzungsdauer</th><th className="number">AfA {jahr}</th><th /></tr></thead>
            <tbody>
              {uebersicht.anlagen.map((a) => {
                const afaDiesesJahr = a.afa_plan.find((p) => p.jahr === jahr)?.afa_betrag ?? "0.00";
                return (
                  <Fragment key={a.id}>
                    <tr>
                      <td>{a.bezeichnung}{a.ist_gwg && <span className="tag-unklar" style={{ marginLeft: 8 }}>GWG</span>}</td>
                      <td>{formatDate(a.anschaffungsdatum)}</td>
                      <td className="number">{formatMoney(a.anschaffungskosten_netto)}</td>
                      <td>{a.ist_gwg ? "Sofort" : `${a.nutzungsdauer_jahre} Jahre`}</td>
                      <td className="number">{formatMoney(afaDiesesJahr)}</td>
                      <td>
                        <button type="button" className="auth-link" onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}>
                          {expandedId === a.id ? "Plan schließen" : "AfA-Plan"}
                        </button>
                      </td>
                    </tr>
                    {expandedId === a.id && (
                      <tr>
                        <td colSpan={6}>
                          <table className="positions-table">
                            <thead><tr><th>Jahr</th><th className="number">AfA-Betrag</th><th className="number">Restbuchwert Ende</th></tr></thead>
                            <tbody>
                              {a.afa_plan.map((p) => (
                                <tr key={p.jahr}><td>{p.jahr}</td><td className="number">{formatMoney(p.afa_betrag)}</td><td className="number">{formatMoney(p.restbuchwert_ende)}</td></tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
