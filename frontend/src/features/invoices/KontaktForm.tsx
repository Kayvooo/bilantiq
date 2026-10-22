import { useState, type FormEvent } from "react";
import { ApiError } from "../auth/api";
import { createKontakt, type Kontakt } from "./api";
import { KontaktFelder } from "./KontaktFelder";
import { formularZuEingabe, LEERES_KONTAKT_FORMULAR, type KontaktFormular } from "./kontaktFormular";

interface Props {
  accessToken: string;
  onCreated: (kontakt: Kontakt) => void;
  onCancel: () => void;
}

export function KontaktForm({ accessToken, onCreated, onCancel }: Props) {
  const [form, setForm] = useState<KontaktFormular>(LEERES_KONTAKT_FORMULAR);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  const zeigtErRechnungsHinweis = form.land === "DE" && form.ist_geschaeftskunde;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      onCreated(await createKontakt(accessToken, formularZuEingabe(form)));
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Kontakt konnte nicht angelegt werden.");
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <h2>Neuer Kontakt</h2>
      <KontaktFelder form={form} onChange={setForm} idPrefix="k" />

      {zeigtErRechnungsHinweis && (
        <p className="hinweis">
          Dieser Kontakt ist ein deutsches B2B-Geschäft. Seit 1.1.2025 muss die Rechnung als E-Rechnung empfangbar sein.
        </p>
      )}

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <div className="actions">
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Wird angelegt …" : "Kontakt anlegen"}
        </button>
        <button type="button" className="auth-link" onClick={onCancel} disabled={status === "loading"}>
          Abbrechen
        </button>
      </div>
    </form>
  );
}
