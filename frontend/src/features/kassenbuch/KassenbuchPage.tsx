import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { createKassenbuchEintrag, getKassenbuch, type KassenbuchUebersicht } from "./api";

interface Props { accessToken: string; onBack: () => void }

function heute(): string {
  return new Date().toISOString().slice(0, 10);
}

export function KassenbuchPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [uebersicht, setUebersicht] = useState<KassenbuchUebersicht | null>(null);

  const [datum, setDatum] = useState(heute());
  const [typ, setTyp] = useState<"einnahme" | "ausgabe">("einnahme");
  const [betrag, setBetrag] = useState("0.00");
  const [beschreibung, setBeschreibung] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setStatus("loading");
    setError("");
    try {
      setUebersicht(await getKassenbuch(accessToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kassenbuch konnte nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      await createKassenbuchEintrag(accessToken, { datum, typ, betrag, beschreibung });
      setBeschreibung("");
      setBetrag("0.00");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Buchung konnte nicht angelegt werden.");
    } finally {
      setCreating(false);
    }
  }

  if (status === "loading") return <PageState label="Kassenbuch wird geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={load} />;
  if (!uebersicht) return null;

  return (
    <div className="invoices-page">
      <PageHeader title="Kassenbuch" description="Manuelle Bar-Ein- und Auszahlungen, ohne Bankanbindung." onBack={onBack} />

      <div className="panel dashboard-summary">
        <p className="dashboard-summary-label">Aktueller Kassenbestand</p>
        <p className="dashboard-summary-value">{formatMoney(uebersicht.aktueller_kassenbestand)}</p>
      </div>

      {error && <p className="auth-error" role="alert">{error}</p>}

      <p className="hinweis">
        Buchungen sind unveränderlich (GoBD-Kassenführung) — eine Fehlbuchung wird durch eine
        Gegenbuchung korrigiert, nicht nachträglich verändert oder gelöscht.
      </p>

      <form className="panel" onSubmit={handleSubmit}>
        <h2>Neue Buchung</h2>
        <div className="field-row">
          <div>
            <label htmlFor="kb-datum">Datum</label>
            <input id="kb-datum" type="date" value={datum} onChange={(e) => setDatum(e.target.value)} required />
          </div>
          <div>
            <label htmlFor="kb-typ">Art</label>
            <select id="kb-typ" value={typ} onChange={(e) => setTyp(e.target.value as typeof typ)}>
              <option value="einnahme">Einnahme</option>
              <option value="ausgabe">Ausgabe</option>
            </select>
          </div>
          <div>
            <label htmlFor="kb-betrag">Betrag</label>
            <input id="kb-betrag" value={betrag} onChange={(e) => setBetrag(e.target.value)} required />
          </div>
        </div>
        <label htmlFor="kb-beschreibung">Beschreibung</label>
        <input id="kb-beschreibung" value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} placeholder="z.B. Trinkgeld, Portokasse" required />
        <button type="submit" disabled={creating}>{creating ? "Wird gebucht …" : "Buchen"}</button>
      </form>

      <h2 className="section-title">Buchungen</h2>
      {uebersicht.eintraege.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Buchung</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Lege oben die erste Kassenbuchung an.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Datum</th><th>Art</th><th>Beschreibung</th><th className="number">Betrag</th><th className="number">Saldo</th></tr></thead>
            <tbody>
              {uebersicht.eintraege.map((e) => (
                <tr key={e.id}>
                  <td>{formatDate(e.datum)}</td>
                  <td>{e.typ === "einnahme" ? "Einnahme" : "Ausgabe"}</td>
                  <td>{e.beschreibung}</td>
                  <td className="number">{e.typ === "einnahme" ? "" : "−"}{formatMoney(e.betrag)}</td>
                  <td className="number">{formatMoney(e.saldo_nach_buchung)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
