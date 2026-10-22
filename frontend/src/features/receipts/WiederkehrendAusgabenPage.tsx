import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import {
  createWiederkehrendeAusgabe, deaktiviereWiederkehrendeAusgabe, erzeugeFaelligeAusgaben,
  listWiederkehrendeAusgaben, type WiederkehrendeAusgabe,
} from "./api";

interface Props { accessToken: string; onBack: () => void }

const EMPTY_FORM = { bezeichnung: "", anbieter: "", betrag: "0.00", ust_satz: "19.00", kategorie: "", intervall: "monatlich" as const, naechstes_datum: new Date().toISOString().slice(0, 10), enddatum: "" };
const INTERVALL_LABEL: Record<string, string> = { monatlich: "Monatlich", quartalsweise: "Quartalsweise", jaehrlich: "Jährlich" };

export function WiederkehrendAusgabenPage({ accessToken, onBack }: Props) {
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [vorlagen, setVorlagen] = useState<WiederkehrendeAusgabe[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [erzeugen, setErzeugen] = useState<"idle" | "loading">("idle");
  const [erzeugtHinweis, setErzeugtHinweis] = useState("");

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setVorlagen(await listWiederkehrendeAusgaben(accessToken));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Wiederkehrende Ausgaben konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      await createWiederkehrendeAusgabe(accessToken, { ...form, enddatum: form.enddatum || null });
      setForm(EMPTY_FORM);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Vorlage konnte nicht angelegt werden.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeaktivieren(id: string) {
    setBusyId(id);
    setError("");
    try {
      await deaktiviereWiederkehrendeAusgabe(accessToken, id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deaktivieren ist fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleErzeugen() {
    setErzeugen("loading");
    setError("");
    setErzeugtHinweis("");
    try {
      const ergebnis = await erzeugeFaelligeAusgaben(accessToken);
      setErzeugtHinweis(
        ergebnis.anzahl === 0 ? "Keine fälligen Vorlagen — nichts zu erzeugen." : `${ergebnis.anzahl} Ausgabe(n) gebucht. Zu finden unter Belege → Ausgaben.`,
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erzeugen ist fehlgeschlagen.");
    } finally {
      setErzeugen("idle");
    }
  }

  if (loadStatus === "loading") return <PageState label="Wiederkehrende Ausgaben werden geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader
        title="Wiederkehrende Ausgaben"
        description="Vorlagen für Kosten, die in festem Abstand automatisch gebucht werden."
        onBack={onBack}
        action={
          <button type="button" className="button-secondary" disabled={erzeugen === "loading"} onClick={handleErzeugen}>
            {erzeugen === "loading" ? "Wird geprüft …" : "Fällige jetzt buchen"}
          </button>
        }
      />

      {error && <p className="auth-error" role="alert">{error}</p>}
      {erzeugtHinweis && <p className="hinweis">{erzeugtHinweis}</p>}

      <p className="hinweis">
        Automatisch gebuchte Ausgaben haben keinen hochgeladenen Beleg. Für die GoBD-Belegpflicht empfiehlt es
        sich, die tatsächliche Rechnung des Anbieters trotzdem separat aufzubewahren.
      </p>

      <form className="panel" onSubmit={handleCreate}>
        <h2>Neue Vorlage</h2>
        <div className="field-row">
          <div>
            <label htmlFor="wka-bezeichnung">Bezeichnung</label>
            <input id="wka-bezeichnung" value={form.bezeichnung} onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })} placeholder="z.B. Cloud-Hosting" required />
          </div>
          <div>
            <label htmlFor="wka-anbieter">Anbieter</label>
            <input id="wka-anbieter" value={form.anbieter} onChange={(e) => setForm({ ...form, anbieter: e.target.value })} required />
          </div>
        </div>
        <div className="field-row">
          <div>
            <label htmlFor="wka-betrag">Betrag (brutto)</label>
            <input id="wka-betrag" value={form.betrag} onChange={(e) => setForm({ ...form, betrag: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="wka-ust">USt %</label>
            <input id="wka-ust" value={form.ust_satz} onChange={(e) => setForm({ ...form, ust_satz: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="wka-kategorie">Kategorie</label>
            <input id="wka-kategorie" value={form.kategorie} onChange={(e) => setForm({ ...form, kategorie: e.target.value })} placeholder="z.B. Software/IT" required />
          </div>
        </div>
        <div className="field-row">
          <div>
            <label htmlFor="wka-intervall">Intervall</label>
            <select id="wka-intervall" value={form.intervall} onChange={(e) => setForm({ ...form, intervall: e.target.value as typeof form.intervall })}>
              <option value="monatlich">Monatlich</option>
              <option value="quartalsweise">Quartalsweise</option>
              <option value="jaehrlich">Jährlich</option>
            </select>
          </div>
          <div>
            <label htmlFor="wka-naechstes">Erste Buchung am</label>
            <input id="wka-naechstes" type="date" value={form.naechstes_datum} onChange={(e) => setForm({ ...form, naechstes_datum: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="wka-ende">Ende (optional)</label>
            <input id="wka-ende" type="date" value={form.enddatum} onChange={(e) => setForm({ ...form, enddatum: e.target.value })} />
          </div>
        </div>
        <button type="submit" disabled={creating}>{creating ? "Wird angelegt …" : "Vorlage anlegen"}</button>
      </form>

      <h2 className="section-title">Alle Vorlagen</h2>
      {vorlagen.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Vorlage</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Lege oben die erste wiederkehrende Ausgabe an.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Bezeichnung</th><th>Anbieter</th><th>Intervall</th><th>Nächstes Datum</th><th className="number">Betrag</th><th>Status</th><th /></tr></thead>
            <tbody>
              {vorlagen.map((v) => (
                <tr key={v.id}>
                  <td>{v.bezeichnung}</td>
                  <td>{v.anbieter}</td>
                  <td>{INTERVALL_LABEL[v.intervall]}</td>
                  <td>{formatDate(v.naechstes_datum)}</td>
                  <td className="number">{formatMoney(v.betrag)}</td>
                  <td>{v.aktiv ? "Aktiv" : "Beendet"}</td>
                  <td>
                    {v.aktiv && (
                      <button type="button" className="auth-link danger" disabled={busyId === v.id} onClick={() => handleDeaktivieren(v.id)}>
                        Beenden
                      </button>
                    )}
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
