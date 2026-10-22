import { useEffect, useState, type FormEvent } from "react";
import { mitBestaetigung } from "./bestaetigung";
import { GroupedListRow, GroupedListSection } from "../../components/GroupedList";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { useRollenStatus } from "../../lib/useIstInhaber";
import { ApiError, getMandant, updateMandant, type Mandant } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
  onOpenEuer: () => void;
  onOpenUstva: () => void;
  onOpenSusa: () => void;
  onOpenBwa: () => void;
}

const EMPTY_FORM = { steuerberater_name: "", steuerberater_email: "", steuerberater_telefon: "" };
type FormState = typeof EMPTY_FORM;

function toForm(mandant: Mandant): FormState {
  return {
    steuerberater_name: mandant.steuerberater_name ?? "",
    steuerberater_email: mandant.steuerberater_email ?? "",
    steuerberater_telefon: mandant.steuerberater_telefon ?? "",
  };
}

export function SteuerberaterPage({ accessToken, onBack, onOpenEuer, onOpenUstva, onOpenSusa, onOpenBwa }: Props) {
  const rolle = useRollenStatus(accessToken);
  const schreibgeschuetzt = rolle !== "inhaber"; // Stammdaten des Mandanten aendert das Backend nur fuer den Inhaber
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setForm(toForm(await getMandant(accessToken)));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Steuerberater-Daten konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaveStatus("saving");
    setError("");
    try {
      setForm(toForm(await mitBestaetigung(accessToken, "iban_aendern", (h) => updateMandant(accessToken, form, h))));
      setSaveStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Steuerberater-Daten konnten nicht gespeichert werden.");
      setSaveStatus("error");
    }
  }

  if (loadStatus === "loading") return <PageState label="Wird geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader title="Mein Steuerberater" description="Kontakt deiner Kanzlei und schneller Zugriff auf die Auswertungen, die sie brauchen." onBack={onBack} />

      {rolle === "mitglied" && <p className="auth-hint" role="status">Die Kanzleidaten darf nur der Inhaber des Kontos ändern; du kannst sie hier ansehen.</p>}
      {error && <p className="auth-error" role="alert">{error}</p>}
      {saveStatus === "saved" && <p className="auth-hint" role="status">Gespeichert.</p>}

      <form className="panel" onSubmit={handleSubmit}>
        <h2>Kontakt</h2>
        <label htmlFor="stb-name">Name / Kanzlei</label>
        <input id="stb-name" readOnly={schreibgeschuetzt} value={form.steuerberater_name} onChange={(e) => setForm({ ...form, steuerberater_name: e.target.value })} placeholder="z.B. Kanzlei Mustermann" />

        <div className="field-row">
          <div>
            <label htmlFor="stb-email">E-Mail</label>
            <input id="stb-email" readOnly={schreibgeschuetzt} type="email" value={form.steuerberater_email} onChange={(e) => setForm({ ...form, steuerberater_email: e.target.value })} />
          </div>
          <div>
            <label htmlFor="stb-telefon">Telefon</label>
            <input id="stb-telefon" readOnly={schreibgeschuetzt} value={form.steuerberater_telefon} onChange={(e) => setForm({ ...form, steuerberater_telefon: e.target.value })} />
          </div>
        </div>

        {!schreibgeschuetzt && (
          <button type="submit" disabled={saveStatus === "saving"}>
            {saveStatus === "saving" ? "Wird gespeichert …" : "Speichern"}
          </button>
        )}
      </form>

      <GroupedListSection title="Auswertungen für die Kanzlei">
        <GroupedListRow label="Einnahmen-Überschuss-Rechnung" description="Inkl. DATEV-Export" onClick={onOpenEuer} />
        <GroupedListRow label="Umsatzsteuervoranmeldung" onClick={onOpenUstva} />
        <GroupedListRow label="Summen- und Saldenliste" onClick={onOpenSusa} />
        <GroupedListRow label="BWA" onClick={onOpenBwa} />
      </GroupedListSection>
    </div>
  );
}
