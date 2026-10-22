import { useState, type FormEvent } from "react";
import { ApiError, loginMfa } from "./api";

interface Props {
  preAuthToken: string;
  onVerified: (accessToken: string) => void;
}

export function MfaChallenge({ preAuthToken, onVerified }: Props) {
  const [code, setCode] = useState("");
  const [rememberDevice, setRememberDevice] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const result = await loginMfa(preAuthToken, code, rememberDevice);
      onVerified(result.access_token);
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Der Code konnte nicht bestätigt werden.");
    }
  }

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Code aus der Authenticator-App</h1>

      <label htmlFor="challenge-code">6-stelliger Code</label>
      <input
        id="challenge-code"
        inputMode="numeric"
        pattern="[0-9]{6}"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        required
        readOnly={status === "loading"}
        autoFocus
      />

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={rememberDevice}
          onChange={(e) => setRememberDevice(e.target.checked)}
          disabled={status === "loading"}
        />
        Dieses Gerät 30 Tage merken
      </label>

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <button type="submit" disabled={status === "loading"}>
        {status === "loading" ? "Wird geprüft …" : "Anmelden"}
      </button>
    </form>
  );
}
