import { useState, type FormEvent } from "react";
import { ApiError, login, type PreAuthResponse } from "./api";

interface Props {
  onLoggedIn: (result: PreAuthResponse) => void;
  onSwitchToRegister: () => void;
  onForgotPassword: () => void;
}

export function LoginForm({ onLoggedIn, onSwitchToRegister, onForgotPassword }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const result = await login(email, password);
      onLoggedIn(result);
    } catch (err) {
      setStatus("error");
      // Same generic message the backend uses — never reveal whether the account exists or is locked.
      setError(err instanceof ApiError ? err.message : "Anmeldung ist fehlgeschlagen.");
    }
  }

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Anmelden</h1>

      <label htmlFor="login-email">E-Mail</label>
      <input
        id="login-email"
        name="email" autoComplete="username" autoCapitalize="none"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        readOnly={status === "loading"}
      />

      <label htmlFor="login-password">Passwort</label>
      <input
        id="login-password"
        name="password" autoComplete="current-password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        readOnly={status === "loading"}
      />

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <button type="submit" disabled={status === "loading"}>
        {status === "loading" ? "Wird geprüft …" : "Anmelden"}
      </button>

      <button type="button" className="auth-link" onClick={onForgotPassword} disabled={status === "loading"}>
        Passwort vergessen?
      </button>

      <button type="button" className="auth-link" onClick={onSwitchToRegister} disabled={status === "loading"}>
        Noch kein Konto? Registrieren
      </button>
    </form>
  );
}

