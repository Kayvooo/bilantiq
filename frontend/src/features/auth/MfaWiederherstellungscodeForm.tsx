import { useState, type FormEvent } from "react";
import { ApiError } from "./api";
import { loginMitWiederherstellungscode } from "./sicherheitApi";
import "./wiederherstellung.css";

interface Props {
  preAuthToken: string;
  onVerified: (accessToken: string) => void;
  onZurueck: () => void;
}

/** Anmeldung mit einem Wiederherstellungscode statt des Codes aus der Authenticator-App. */
export function MfaWiederherstellungscodeForm({ preAuthToken, onVerified, onZurueck }: Props) {
  const [code, setCode] = useState("");
  const [rememberDevice, setRememberDevice] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const result = await loginMitWiederherstellungscode(preAuthToken, code.trim(), rememberDevice);
      onVerified(result.access_token);
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Der Code konnte nicht bestätigt werden.");
    }
  }

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Wiederherstellungscode</h1>
      <p className="auth-hint">
        Gib einen deiner Wiederherstellungscodes ein, zum Beispiel wenn du dein Handy verloren hast. Jeder Code funktioniert
        nur einmal. Danach kannst du in den Einstellungen die Zwei-Faktor-Anmeldung auf einem neuen Gerät einrichten.
      </p>

      <label htmlFor="recovery-code">Wiederherstellungscode</label>
      <input
        id="recovery-code"
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        placeholder="XXXXX-XXXXX"
        maxLength={32}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        required
        readOnly={status === "loading"}
        autoFocus
      />

      <label className="checkbox-row">
        <input type="checkbox" checked={rememberDevice} onChange={(e) => setRememberDevice(e.target.checked)} disabled={status === "loading"} />
        Dieses Gerät 30 Tage merken
      </label>

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <button type="submit" disabled={status === "loading"}>{status === "loading" ? "Wird geprüft …" : "Anmelden"}</button>
      <button type="button" className="auth-link" onClick={onZurueck} disabled={status === "loading"}>Stattdessen Code aus der Authenticator-App eingeben</button>
    </form>
  );
}
