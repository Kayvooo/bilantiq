import { Fragment, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import {
  createEinnahme,
  listEinnahmen,
  updateEinnahme,
  type SonstigeEinnahme,
  type SonstigeEinnahmePayload,
} from "./api";

interface Props { accessToken: string; onBack: () => void }

function heute(): string {
  const datum = new Date();
  const offset = datum.getTimezoneOffset() * 60_000;
  return new Date(datum.getTime() - offset).toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  bezeichnung: "",
  betrag_brutto: "0.00",
  ust_satz: "19.00",
  datum: heute(),
  verwendungszweck: "",
};
type FormState = typeof EMPTY_FORM;

function toForm(einnahme: SonstigeEinnahme): FormState {
  return { ...einnahme, verwendungszweck: einnahme.verwendungszweck ?? "" };
}

function toPayload(form: FormState): SonstigeEinnahmePayload {
  return { ...form, verwendungszweck: form.verwendungszweck || null };
}

function EinnahmeFields({ form, onChange, idPrefix }: {
  form: FormState;
  onChange: (form: FormState) => void;
  idPrefix: string;
}) {
  return (
    <>
      <div className="field-row">
        <div>
          <label htmlFor={`${idPrefix}-bezeichnung`}>Bezeichnung</label>
          <input
            id={`${idPrefix}-bezeichnung`}
            value={form.bezeichnung}
            onChange={(event) => onChange({ ...form, bezeichnung: event.target.value })}
            placeholder="z. B. Provision"
            required
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-betrag`}>Betrag (brutto)</label>
          <input
            id={`${idPrefix}-betrag`}
            type="number"
            min="0.01"
            step="0.01"
            value={form.betrag_brutto}
            onChange={(event) => onChange({ ...form, betrag_brutto: event.target.value })}
            required
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-ust`}>USt %</label>
          <input
            id={`${idPrefix}-ust`}
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={form.ust_satz}
            onChange={(event) => onChange({ ...form, ust_satz: event.target.value })}
            required
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-datum`}>Datum</label>
          <input
            id={`${idPrefix}-datum`}
            type="date"
            value={form.datum}
            onChange={(event) => onChange({ ...form, datum: event.target.value })}
            required
          />
        </div>
      </div>
      <label htmlFor={`${idPrefix}-verwendungszweck`}>Verwendungszweck (optional)</label>
      <input
        id={`${idPrefix}-verwendungszweck`}
        value={form.verwendungszweck}
        onChange={(event) => onChange({ ...form, verwendungszweck: event.target.value })}
        maxLength={500}
        placeholder="z. B. Partnerprogramm Mai"
      />
    </>
  );
}

export function EinnahmenPage({ accessToken, onBack }: Props) {
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [einnahmen, setEinnahmen] = useState<SonstigeEinnahme[]>([]);
  const [createForm, setCreateForm] = useState<FormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setEinnahmen(await listEinnahmen(accessToken));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einnahmen konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      await createEinnahme(accessToken, toPayload(createForm));
      setCreateForm({ ...EMPTY_FORM, datum: heute() });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einnahme konnte nicht angelegt werden.");
    } finally {
      setCreating(false);
    }
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!editId) return;
    setSaving(true);
    setError("");
    try {
      await updateEinnahme(accessToken, editId, toPayload(editForm));
      setEditId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einnahme konnte nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  }

  if (loadStatus === "loading") return <PageState label="Einnahmen werden geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader title="Sonstige Einnahmen" description="Betriebliche Einnahmen außerhalb deiner Rechnungen erfassen." onBack={onBack} />
      {error && <p className="auth-error" role="alert">{error}</p>}

      <form className="panel" onSubmit={handleCreate}>
        <h2>Neue Einnahme</h2>
        <EinnahmeFields form={createForm} onChange={setCreateForm} idPrefix="new-income" />
        <button type="submit" disabled={creating}>{creating ? "Wird angelegt …" : "Einnahme anlegen"}</button>
      </form>

      <h2 className="section-title">Alle sonstigen Einnahmen</h2>
      {einnahmen.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine sonstigen Einnahmen</h2>
          <p className="auth-hint" style={{ margin: 0 }}>Erfasse oben deine erste Einnahme.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Datum</th><th>Bezeichnung</th><th>Verwendungszweck</th><th className="number">Brutto</th><th className="number">USt</th><th /></tr></thead>
            <tbody>
              {einnahmen.map((einnahme) => (
                <Fragment key={einnahme.id}>
                  <tr>
                    <td>{formatDate(einnahme.datum)}</td>
                    <td>{einnahme.bezeichnung}</td>
                    <td>{einnahme.verwendungszweck || "—"}</td>
                    <td className="number">{formatMoney(einnahme.betrag_brutto)}</td>
                    <td className="number">{Number(einnahme.ust_satz).toLocaleString("de-DE")} %</td>
                    <td><button type="button" className="auth-link" onClick={() => {
                      if (editId === einnahme.id) setEditId(null);
                      else { setEditId(einnahme.id); setEditForm(toForm(einnahme)); }
                    }}>{editId === einnahme.id ? "Schließen" : "Bearbeiten"}</button></td>
                  </tr>
                  {editId === einnahme.id && (
                    <tr><td colSpan={6}>
                      <form className="confirm-row" onSubmit={handleSave}>
                        <EinnahmeFields form={editForm} onChange={setEditForm} idPrefix={`edit-income-${einnahme.id}`} />
                        <button type="submit" disabled={saving}>{saving ? "Wird gespeichert …" : "Speichern"}</button>
                      </form>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
