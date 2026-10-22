import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import {
  createWiederkehrendeRechnung, deaktiviereWiederkehrendeRechnung, erzeugeFaelligeRechnungen,
  listKontakte, listWiederkehrendeRechnungen,
  type InvoicePosition, type Kontakt, type WiederkehrendeRechnung,
} from "./api";

interface Props { accessToken: string; onBack: () => void }

const LEER_POSITION: InvoicePosition = { beschreibung: "", menge: "1", einzelpreis: "0.00", ust_satz: "19.00" };

function heute(): string {
  return new Date().toISOString().slice(0, 10);
}

const INTERVALL_LABEL: Record<string, string> = { monatlich: "Monatlich", quartalsweise: "Quartalsweise", jaehrlich: "Jährlich" };

export function WiederkehrendPage({ accessToken, onBack }: Props) {
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [kontakte, setKontakte] = useState<Kontakt[]>([]);
  const [vorlagen, setVorlagen] = useState<WiederkehrendeRechnung[]>([]);

  const [kontaktId, setKontaktId] = useState("");
  const [bezeichnung, setBezeichnung] = useState("");
  const [intervall, setIntervall] = useState<"monatlich" | "quartalsweise" | "jaehrlich">("monatlich");
  const [naechstesDatum, setNaechstesDatum] = useState(heute());
  const [enddatum, setEnddatum] = useState("");
  const [positionen, setPositionen] = useState<InvoicePosition[]>([{ ...LEER_POSITION }]);
  const [creating, setCreating] = useState(false);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [erzeugen, setErzeugen] = useState<"idle" | "loading">("idle");
  const [erzeugtHinweis, setErzeugtHinweis] = useState("");

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      const [k, v] = await Promise.all([listKontakte(accessToken, { typ: "kunde" }), listWiederkehrendeRechnungen(accessToken)]);
      setKontakte(k);
      setVorlagen(v);
      setKontaktId((current) => current || k[0]?.id || "");
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Wiederkehrende Rechnungen konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  function updatePosition(index: number, field: keyof InvoicePosition, value: string) {
    setPositionen((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)));
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!kontaktId) return;
    setCreating(true);
    setError("");
    try {
      await createWiederkehrendeRechnung(accessToken, {
        kontakt_id: kontaktId, bezeichnung, intervall, naechstes_datum: naechstesDatum,
        enddatum: enddatum || null, positionen,
      });
      setBezeichnung("");
      setPositionen([{ ...LEER_POSITION }]);
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
      await deaktiviereWiederkehrendeRechnung(accessToken, id);
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
      const ergebnis = await erzeugeFaelligeRechnungen(accessToken);
      setErzeugtHinweis(
        ergebnis.anzahl === 0
          ? "Keine fälligen Vorlagen — nichts zu erzeugen."
          : `${ergebnis.anzahl} Rechnungsentwurf/-entwürfe erzeugt. Zu finden unter Rechnungen.`,
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erzeugen ist fehlgeschlagen.");
    } finally {
      setErzeugen("idle");
    }
  }

  if (loadStatus === "loading") return <PageState label="Wiederkehrende Rechnungen werden geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader
        title="Wiederkehrende Rechnungen"
        description="Vorlagen für Rechnungen, die in festem Abstand als Entwurf angelegt werden."
        onBack={onBack}
        action={
          <button type="button" className="button-secondary" disabled={erzeugen === "loading"} onClick={handleErzeugen}>
            {erzeugen === "loading" ? "Wird geprüft …" : "Fällige jetzt erzeugen"}
          </button>
        }
      />

      {error && <p className="auth-error" role="alert">{error}</p>}
      {erzeugtHinweis && <p className="hinweis">{erzeugtHinweis}</p>}

      <p className="hinweis">
        Erzeugte Rechnungen bleiben Entwürfe — sie werden nie automatisch finalisiert oder versendet.
        Diese Seite muss also regelmäßig besucht (oder „Fällige jetzt erzeugen" geklickt) werden, es läuft
        kein Hintergrundjob.
      </p>

      {kontakte.length === 0 ? (
        <div className="empty-state">
          <h2>Noch kein Kontakt vorhanden</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Lege zuerst unter Kontakte einen Kunden an.</p>
        </div>
      ) : (
        <form className="panel" onSubmit={handleCreate}>
          <h2>Neue Vorlage</h2>
          <div className="field-row">
            <div>
              <label htmlFor="wk-bezeichnung">Bezeichnung</label>
              <input id="wk-bezeichnung" value={bezeichnung} onChange={(e) => setBezeichnung(e.target.value)} placeholder="z.B. Hosting-Abo" required />
            </div>
            <div>
              <label htmlFor="wk-kontakt">Kunde</label>
              <select id="wk-kontakt" value={kontaktId} onChange={(e) => setKontaktId(e.target.value)}>
                {kontakte.map((k) => (<option key={k.id} value={k.id}>{k.name}</option>))}
              </select>
            </div>
          </div>
          <div className="field-row">
            <div>
              <label htmlFor="wk-intervall">Intervall</label>
              <select id="wk-intervall" value={intervall} onChange={(e) => setIntervall(e.target.value as typeof intervall)}>
                <option value="monatlich">Monatlich</option>
                <option value="quartalsweise">Quartalsweise</option>
                <option value="jaehrlich">Jährlich</option>
              </select>
            </div>
            <div>
              <label htmlFor="wk-naechstes">Erste Rechnung am</label>
              <input id="wk-naechstes" type="date" value={naechstesDatum} onChange={(e) => setNaechstesDatum(e.target.value)} required />
            </div>
            <div>
              <label htmlFor="wk-ende">Ende (optional)</label>
              <input id="wk-ende" type="date" value={enddatum} onChange={(e) => setEnddatum(e.target.value)} />
            </div>
          </div>

          <div className="table-scroll">
            <table className="positions-table">
              <thead><tr><th>Beschreibung</th><th>Menge</th><th>Einzelpreis</th><th>USt %</th></tr></thead>
              <tbody>
                {positionen.map((p, i) => (
                  <tr key={i}>
                    <td><input aria-label={`Beschreibung, Position ${i + 1}`} value={p.beschreibung} onChange={(e) => updatePosition(i, "beschreibung", e.target.value)} required /></td>
                    <td><input aria-label={`Menge, Position ${i + 1}`} value={p.menge} onChange={(e) => updatePosition(i, "menge", e.target.value)} required /></td>
                    <td><input aria-label={`Einzelpreis, Position ${i + 1}`} value={p.einzelpreis} onChange={(e) => updatePosition(i, "einzelpreis", e.target.value)} required /></td>
                    <td><input aria-label={`Umsatzsteuersatz in Prozent, Position ${i + 1}`} value={p.ust_satz} onChange={(e) => updatePosition(i, "ust_satz", e.target.value)} required /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="auth-link" onClick={() => setPositionen((prev) => [...prev, { ...LEER_POSITION }])}>+ Position</button>

          <button type="submit" disabled={creating}>{creating ? "Wird angelegt …" : "Vorlage anlegen"}</button>
        </form>
      )}

      <h2 className="section-title">Alle Vorlagen</h2>
      {vorlagen.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Vorlage</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Lege oben die erste wiederkehrende Rechnung an.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Bezeichnung</th><th>Kunde</th><th>Intervall</th><th>Nächstes Datum</th><th className="number">Betrag netto</th><th>Status</th><th /></tr></thead>
            <tbody>
              {vorlagen.map((v) => {
                const netto = v.positionen.reduce((sum, p) => sum + Number(p.menge) * Number(p.einzelpreis), 0);
                return (
                  <tr key={v.id}>
                    <td>{v.bezeichnung}</td>
                    <td>{v.kontakt_name}</td>
                    <td>{INTERVALL_LABEL[v.intervall]}</td>
                    <td>{formatDate(v.naechstes_datum)}</td>
                    <td className="number">{formatMoney(netto.toFixed(2))}</td>
                    <td>{v.aktiv ? "Aktiv" : "Beendet"}</td>
                    <td>
                      {v.aktiv && (
                        <button type="button" className="auth-link danger" disabled={busyId === v.id} onClick={() => handleDeaktivieren(v.id)}>
                          Beenden
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
