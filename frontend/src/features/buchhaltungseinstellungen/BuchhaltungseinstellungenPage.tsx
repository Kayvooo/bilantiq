import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { useIstInhaber } from "../../lib/useIstInhaber";
import { ApiError } from "../auth/api";
import { NummernkreisPanel } from "../nummernkreis/NummernkreisPanel";
import {
  getBuchhaltungseinstellungen,
  putBuchhaltungseinstellungen,
  DEFAULT_BUCHHALTUNGSEINSTELLUNGEN,
  type Buchhaltungseinstellungen,
} from "./api";

interface Props { accessToken: string; onBack: () => void }

export function BuchhaltungseinstellungenPage({ accessToken, onBack }: Props) {
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [form, setForm] = useState<Buchhaltungseinstellungen>(DEFAULT_BUCHHALTUNGSEINSTELLUNGEN);
  const [error, setError] = useState("");
  const istInhaber = useIstInhaber(accessToken);

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setForm(await getBuchhaltungseinstellungen(accessToken));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einstellungen konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaveStatus("saving");
    setError("");
    try {
      setForm(await putBuchhaltungseinstellungen(accessToken, form));
      setSaveStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einstellungen konnten nicht gespeichert werden.");
      setSaveStatus("idle");
    }
  }

  if (loadStatus === "loading") return <PageState label="Buchhaltungseinstellungen werden geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader title="Buchhaltung" description="Vorbelegungen für neue Rechnungen und Angebote." onBack={onBack} />
      {error && <p className="auth-error" role="alert">{error}</p>}
      {saveStatus === "saved" && <p className="auth-hint" role="status">Gespeichert.</p>}

      <form className="panel" onSubmit={handleSubmit}>
        <h2>Standardwerte</h2>
        <p className="auth-hint">Diese Werte werden beim Öffnen neuer Formulare vorgeschlagen und können dort weiterhin geändert werden.</p>
        <div className="field-row">
          <div>
            <label htmlFor="bookkeeping-payment-days">Zahlungsziel in Tagen</label>
            <input
              id="bookkeeping-payment-days"
              type="number"
              min="0"
              max="365"
              value={form.standard_zahlungsziel_tage}
              onChange={(event) => setForm({ ...form, standard_zahlungsziel_tage: Number(event.target.value) })}
              required
            />
          </div>
          <div>
            <label htmlFor="bookkeeping-vat">Standard-USt %</label>
            <input
              id="bookkeeping-vat"
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={form.standard_ust_satz}
              onChange={(event) => setForm({ ...form, standard_ust_satz: event.target.value })}
              disabled={form.kleinunternehmer}
              required
            />
          </div>
        </div>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.kleinunternehmer}
            onChange={(event) => setForm({ ...form, kleinunternehmer: event.target.checked })}
          />
          Kleinunternehmerregelung (§19 UStG): neue Positionen mit 0 % USt vorbelegen
        </label>
        <p className="auth-hint">Die Einstellung ist keine steuerliche Prüfung und erzwingt keinen Steuersatz im Backend.</p>

        <button type="submit" disabled={saveStatus === "saving"}>
          {saveStatus === "saving" ? "Wird gespeichert …" : "Speichern"}
        </button>
      </form>

      <section className="panel">
        <NummernkreisPanel accessToken={accessToken} istInhaber={istInhaber} />
      </section>
    </div>
  );
}
