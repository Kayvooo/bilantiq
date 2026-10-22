import { useState, type FormEvent } from "react";
import { ApiError } from "./api";
import { passwortVergessen } from "./sicherheitApi";
import "./wiederherstellung.css";

interface Props {
  onZurueck: () => void;
}

/** Fordert einen Link zum Zurücksetzen des Passworts an. Die Antwort ist absichtlich immer dieselbe, egal ob es das Konto gibt. */
export function PasswortVergessenForm({ onZurueck }: Props) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "sent">("idle");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      await passwortVergessen(email.trim());
      setStatus("sent");
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Die Anfrage konnte nicht gesendet werden.");
    }
  }

  if (status === "sent") {
    return (
      <div className="auth-card">
        <h1>Prüfe dein Postfach</h1>
        <p className="auth-success" role="status">
          Wenn zu dieser E-Mail-Adresse ein Konto existiert, haben wir einen Link zum Zurücksetzen des Passworts gesendet.
        </p>
        <p className="auth-hint">Der Link ist 60 Minuten gültig und kann nur einmal verwendet werden. Schau bei Bedarf auch im Spam-Ordner nach.</p>
        <button type="button" className="auth-link" onClick={onZurueck}>Zurück zur Anmeldung</button>
      </div>
    );
  }

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Passwort vergessen</h1>
      <p className="auth-hint">Gib die E-Mail-Adresse deines Kontos ein. Wir senden dir einen Link, über den du ein neues Passwort festlegst.</p>

      <label htmlFor="vergessen-email">E-Mail</label>
      <input
        id="vergessen-email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        readOnly={status === "loading"}
        autoFocus
      />

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}

      <button type="submit" disabled={status === "loading"}>{status === "loading" ? "Wird gesendet …" : "Link senden"}</button>
      <button type="button" className="auth-link" onClick={onZurueck} disabled={status === "loading"}>Zurück zur Anmeldung</button>
    </form>
  );
}
