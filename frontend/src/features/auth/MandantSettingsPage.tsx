import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { useRollenStatus } from "../../lib/useIstInhaber";
import { ApiError, getMandant, updateMandant, type Mandant } from "./api";

interface Props { accessToken: string; onBack: () => void }

const EMPTY_FORM = { firmenname: "", ust_id: "", steuernummer: "", adresse: "", datev_beraternummer: "", datev_mandantennummer: "" };

function toForm(mandant: Mandant): typeof EMPTY_FORM {
  return {
    firmenname: mandant.firmenname,
    ust_id: mandant.ust_id ?? "",
    steuernummer: mandant.steuernummer ?? "",
    adresse: mandant.adresse ?? "",
    datev_beraternummer: mandant.datev_beraternummer ?? "",
    datev_mandantennummer: mandant.datev_mandantennummer ?? "",
  };
}

export function MandantSettingsPage({ accessToken, onBack }: Props) {
  const rolle = useRollenStatus(accessToken);
  // Firmen- und Bankdaten stehen auf jeder Rechnung: das Backend laesst nur den Inhaber sie aendern.
  const schreibgeschuetzt = rolle !== "inhaber";
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setForm(toForm(await getMandant(accessToken)));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Firmendaten konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaveStatus("saving");
    setError("");
    try {
      setForm(toForm(await updateMandant(accessToken, form)));
      setSaveStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Firmendaten konnten nicht gespeichert werden.");
      setSaveStatus("error");
    }
  }

  if (loadStatus === "loading") return <PageState label="Firmendaten werden geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader
        title="Firmendaten"
        description="USt-IdNr., Steuernummer und DATEV-Nummern für E-Rechnungen und den DATEV-Export."
        onBack={onBack}
      />

      {rolle === "mitglied" && (
        <p className="auth-hint" role="status">
          Firmen-, Steuer- und DATEV-Daten stehen auf jeder Rechnung. Deshalb darf nur der Inhaber des Kontos sie ändern; du kannst sie hier ansehen.
        </p>
      )}
      {error && <p className="auth-error" role="alert">{error}</p>}
      {saveStatus === "saved" && <p className="auth-hint" role="status">Gespeichert.</p>}

      <form className="panel" onSubmit={handleSubmit}>
        <h2>Firma</h2>
        <div className="field-row">
          <div>
            <label htmlFor="mandant-firmenname">Firmenname</label>
            <input
              id="mandant-firmenname"
              readOnly={schreibgeschuetzt}
              value={form.firmenname}
              onChange={(e) => setForm({ ...form, firmenname: e.target.value })}
              required
            />
          </div>
          <div>
            <label htmlFor="mandant-adresse">Adresse</label>
            <input
              id="mandant-adresse"
              readOnly={schreibgeschuetzt}
              value={form.adresse}
              onChange={(e) => setForm({ ...form, adresse: e.target.value })}
              placeholder="Straße Hausnummer, PLZ Ort"
            />
          </div>
        </div>

        <h2>Steuer</h2>
        <p className="auth-hint">Ohne USt-IdNr. oder Steuernummer kann keine XRechnung erzeugt werden.</p>
        <div className="field-row">
          <div>
            <label htmlFor="mandant-ust-id">USt-IdNr.</label>
            <input
              id="mandant-ust-id"
              readOnly={schreibgeschuetzt}
              value={form.ust_id}
              onChange={(e) => setForm({ ...form, ust_id: e.target.value })}
              placeholder="DE123456789"
            />
          </div>
          <div>
            <label htmlFor="mandant-steuernummer">Steuernummer</label>
            <input
              id="mandant-steuernummer"
              readOnly={schreibgeschuetzt}
              value={form.steuernummer}
              onChange={(e) => setForm({ ...form, steuernummer: e.target.value })}
              placeholder="12/345/67890"
            />
          </div>
        </div>

        <h2>DATEV</h2>
        <p className="auth-hint">Wird in den Kopfzeilen des DATEV-Exports verwendet.</p>
        <div className="field-row">
          <div>
            <label htmlFor="mandant-datev-berater">DATEV-Beraternummer</label>
            <input
              id="mandant-datev-berater"
              readOnly={schreibgeschuetzt}
              value={form.datev_beraternummer}
              onChange={(e) => setForm({ ...form, datev_beraternummer: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="mandant-datev-mandant">DATEV-Mandantennummer</label>
            <input
              id="mandant-datev-mandant"
              readOnly={schreibgeschuetzt}
              value={form.datev_mandantennummer}
              onChange={(e) => setForm({ ...form, datev_mandantennummer: e.target.value })}
            />
          </div>
        </div>

        {!schreibgeschuetzt && (
          <button type="submit" disabled={saveStatus === "saving"}>
            {saveStatus === "saving" ? "Wird gespeichert …" : "Speichern"}
          </button>
        )}
      </form>
    </div>
  );
}
