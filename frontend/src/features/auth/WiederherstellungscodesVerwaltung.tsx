import { useState, type FormEvent } from "react";
import { ApiError } from "./api";
import { wiederherstellungscodesNeu } from "./sicherheitApi";
import { WiederherstellungscodesAnzeige } from "./WiederherstellungscodesAnzeige";
import "./wiederherstellung.css";

interface Props {
  accessToken: string;
  /** Zahl der noch gültigen Codes (null/undefined, wenn nicht bekannt). */
  offen: number | null | undefined;
  /** Nach dem Schließen der Anzeige: Übersicht neu laden. */
  onGeaendert: () => void;
}

/** Status der Wiederherstellungscodes und Neu-Erzeugen (nur mit Passwort + aktuellem Code, alte Codes werden ungültig). */
export function WiederherstellungscodesVerwaltung({ accessToken, offen, onGeaendert }: Props) {
  const [formularOffen, setFormularOffen] = useState(false);
  const [passwort, setPasswort] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState("");
  const [neueCodes, setNeueCodes] = useState<string[] | null>(null);

  async function erzeugen(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFehler("");
    try {
      const antwort = await wiederherstellungscodesNeu(accessToken, passwort, code.trim());
      setNeueCodes(antwort.wiederherstellungscodes);
      setPasswort("");
      setCode("");
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Wiederherstellungscodes konnten nicht erzeugt werden.");
    } finally {
      setBusy(false);
    }
  }

  if (neueCodes) {
    return (
      <div>
        <h3>Neue Wiederherstellungscodes</h3>
        <WiederherstellungscodesAnzeige
          codes={neueCodes}
          weiterLabel="Fertig"
          onWeiter={() => { setNeueCodes(null); setFormularOffen(false); onGeaendert(); }}
        />
      </div>
    );
  }

  const wenige = typeof offen === "number" && offen <= 2;
  return (
    <div>
      <h3>Wiederherstellungscodes</h3>
      <p className="auth-hint">
        {typeof offen === "number" ? <>Noch <strong>{offen}</strong> von 10 Codes gültig. </> : null}
        Mit einem Wiederherstellungscode meldest du dich an, wenn du dein Handy verloren hast.
      </p>
      {wenige && <p className="recovery-warning" role="alert">Es sind nur noch wenige Codes übrig. Erzeuge neue, bevor sie aufgebraucht sind.</p>}
      {!formularOffen ? (
        <button type="button" className="button-secondary" onClick={() => setFormularOffen(true)}>Neue Codes erzeugen</button>
      ) : (
        <form onSubmit={erzeugen}>
          <p className="auth-hint">Die bisherigen Codes werden dabei sofort ungültig.</p>
          <div className="field-row">
            <div>
              <label htmlFor="rc-passwort">Aktuelles Passwort</label>
              <input id="rc-passwort" type="password" autoComplete="current-password" value={passwort} onChange={(e) => setPasswort(e.target.value)} required />
            </div>
            <div>
              <label htmlFor="rc-code">Aktueller Code (6 Stellen) oder Wiederherstellungscode</label>
              <input id="rc-code" autoComplete="one-time-code" maxLength={32} value={code} onChange={(e) => setCode(e.target.value)} required />
            </div>
          </div>
          {fehler && <p className="auth-error" role="alert">{fehler}</p>}
          <div className="actions">
            <button type="submit" disabled={busy}>{busy ? "Wird erzeugt …" : "Neue Codes erzeugen"}</button>
            <button type="button" className="auth-link" onClick={() => { setFormularOffen(false); setFehler(""); }} disabled={busy}>Abbrechen</button>
          </div>
        </form>
      )}
    </div>
  );
}
