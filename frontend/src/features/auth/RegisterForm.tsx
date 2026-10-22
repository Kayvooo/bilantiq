import { useState, type FormEvent } from "react";
import { EINLADUNGSCODE_EINGABE_MAX, EINLADUNGSCODE_LAENGE, normalisiereEinladungscode } from "./einladungscode";
import { ApiError, register, type PreAuthResponse } from "./api";

interface Props {
  onRegistered: (result: PreAuthResponse) => void;
  onSwitchToLogin: () => void;
}

export function RegisterForm({ onRegistered, onSwitchToLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firmenname, setFirmenname] = useState("");
  const [einladungscode, setEinladungscode] = useState("");
  const [zeigeEinladung, setZeigeEinladung] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const result = await register(
        email, password,
        zeigeEinladung ? null : firmenname,
        zeigeEinladung ? normalisiereEinladungscode(einladungscode) : null,
      );
      onRegistered(result);
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Registrierung ist fehlgeschlagen.");
    }
  }

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Konto erstellen</h1>
      <p className="auth-hint">Nach der Registrierung bist du direkt angemeldet. Die Zwei-Faktor-Anmeldung richtest du danach unter Sicherheit &amp; Datenschutz ein, wir empfehlen das dringend.</p>

      {zeigeEinladung ? (
        <>
          <label htmlFor="einladungscode">Einladungscode</label>
          <input
            id="einladungscode"
            value={einladungscode}
            onChange={(e) => setEinladungscode(normalisiereEinladungscode(e.target.value))}
            maxLength={EINLADUNGSCODE_EINGABE_MAX}
            minLength={EINLADUNGSCODE_LAENGE}
            pattern="[0-9A-Za-z]{12}"
            title="Der Einladungscode hat 12 Zeichen (Ziffern und Buchstaben)."
            placeholder="12 Zeichen, z. B. 3F9A1C7D02BE"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            required
            readOnly={status === "loading"}
          />
          <p className="auth-hint">Den Code (12 Zeichen) bekommst du vom Inhaber des Kontos unter „Benutzer &amp; Rechte“.</p>
        </>
      ) : (
        <>
          <label htmlFor="firmenname">Firmenname</label>
          <input
            id="firmenname"
            autoComplete="organization"
            value={firmenname}
            onChange={(e) => setFirmenname(e.target.value)}
            required
            readOnly={status === "loading"}
          />
        </>
      )}

      <button type="button" className="auth-link" onClick={() => setZeigeEinladung((v) => !v)} disabled={status === "loading"}>
        {zeigeEinladung ? "Eigene Firma anlegen statt Einladung" : "Einladungscode statt eigener Firma?"}
      </button>

      <label htmlFor="email">E-Mail</label>
      <input
        id="email"
        name="email" autoComplete="username" autoCapitalize="none"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        readOnly={status === "loading"}
      />

      <label htmlFor="password">Passwort (mind. 12 Zeichen)</label>
      <input
        id="password"
        name="password" autoComplete="new-password"
        type="password"
        minLength={12}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        readOnly={status === "loading"}
      />

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <button type="submit" disabled={status === "loading"}>
        {status === "loading" ? "Wird angelegt …" : "Konto anlegen"}
      </button>

      <button type="button" className="auth-link" onClick={onSwitchToLogin} disabled={status === "loading"}>
        Schon ein Konto? Anmelden
      </button>
    </form>
  );
}

