import { useState, type FormEvent } from "react";
import { ApiError } from "./api";
import { passwortZuruecksetzen } from "./sicherheitApi";
import "./wiederherstellung.css";

interface Props {
  token: string;
  onZurAnmeldung: () => void;
  onNeuAnfordern: () => void;
}

/** Neues Passwort festlegen. Der Token stammt aus dem Link der E-Mail (siehe passwortResetLink.ts). */
export function PasswortZuruecksetzenForm({ token, onZurAnmeldung, onNeuAnfordern }: Props) {
  const [passwort, setPasswort] = useState("");
  const [wiederholung, setWiederholung] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [error, setError] = useState("");
  const [linkUngueltig, setLinkUngueltig] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (passwort !== wiederholung) {
      setStatus("error");
      setError("Die Passwort-Wiederholung stimmt nicht überein.");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      await passwortZuruecksetzen(token, passwort);
      setStatus("done");
    } catch (err) {
      setStatus("error");
      setLinkUngueltig(err instanceof ApiError && err.status === 400);
      setError(err instanceof ApiError ? err.message : "Das Passwort konnte nicht zurückgesetzt werden.");
    }
  }

  if (status === "done") {
    return (
      <div className="auth-card">
        <h1>Passwort geändert</h1>
        <p className="auth-success" role="status">Dein Passwort wurde geändert. Alle bisherigen Sitzungen wurden beendet.</p>
        <p className="auth-hint">Melde dich jetzt mit dem neuen Passwort an. Ist die Zwei-Faktor-Anmeldung eingerichtet, bleibt sie aktiv: Du brauchst weiterhin einen Code oder einen Wiederherstellungscode.</p>
        <button type="button" onClick={onZurAnmeldung}>Zur Anmeldung</button>
      </div>
    );
  }

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Neues Passwort festlegen</h1>
      <p className="auth-hint">Mindestens 12 Zeichen. Nach dem Speichern werden alle Sitzungen beendet.</p>

      <label htmlFor="reset-pw">Neues Passwort</label>
      <input id="reset-pw" type="password" autoComplete="new-password" minLength={12} maxLength={256} value={passwort} onChange={(e) => setPasswort(e.target.value)} required readOnly={status === "loading"} autoFocus />

      <label htmlFor="reset-pw2">Neues Passwort wiederholen</label>
      <input id="reset-pw2" type="password" autoComplete="new-password" minLength={12} maxLength={256} value={wiederholung} onChange={(e) => setWiederholung(e.target.value)} required readOnly={status === "loading"} />

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <button type="submit" disabled={status === "loading"}>{status === "loading" ? "Wird gespeichert …" : "Passwort speichern"}</button>
      {linkUngueltig && <button type="button" className="auth-link" onClick={onNeuAnfordern}>Neuen Link anfordern</button>}
      <button type="button" className="auth-link" onClick={onZurAnmeldung} disabled={status === "loading"}>Zurück zur Anmeldung</button>
    </form>
  );
}
