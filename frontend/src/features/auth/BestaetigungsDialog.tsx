import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, erteileBestaetigung } from "./api";
import { setBestaetigungsOeffner, type BestaetigungsAnfrage } from "./bestaetigung";

const TITEL: Record<BestaetigungsAnfrage["aktion"], string> = {
  iban_aendern: "Änderung der Bankverbindung bestätigen",
  benutzer_verwalten: "Änderung der Zugänge bestätigen",
  gesamtexport: "Gesamtexport bestätigen",
};

/** Einmal im Wurzel-Baum einhaengen. Fragt nach einem aktuellen Code, wenn eine Aktion eine frische Bestaetigung verlangt. */
export function BestaetigungsDialog() {
  const [anfrage, setAnfrage] = useState<BestaetigungsAnfrage | null>(null);
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const eingabeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setBestaetigungsOeffner((neu) => {
      setCode("");
      setFehler("");
      setLaeuft(false);
      setAnfrage(neu);
    });
    return () => setBestaetigungsOeffner(null);
  }, []);

  useEffect(() => {
    if (anfrage) eingabeRef.current?.focus();
  }, [anfrage]);

  function abbrechen() {
    anfrage?.fertig(null);
    setAnfrage(null);
  }

  useEffect(() => {
    if (!anfrage) return;
    function beiTaste(ereignis: KeyboardEvent) {
      if (ereignis.key === "Escape") {
        ereignis.preventDefault();
        anfrage?.fertig(null);
        setAnfrage(null);
      }
    }
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
  }, [anfrage]);

  async function bestaetigen(ereignis: FormEvent) {
    ereignis.preventDefault();
    if (!anfrage) return;
    setLaeuft(true);
    setFehler("");
    try {
      const antwort = await erteileBestaetigung(anfrage.accessToken, anfrage.aktion, code.trim());
      anfrage.fertig(antwort.bestaetigung_token);
      setAnfrage(null);
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Der Code konnte nicht bestätigt werden.");
      setLaeuft(false);
    }
  }

  if (!anfrage) return null;

  return (
    <div className="hinweis-overlay">
      <form className="hinweis-dialog" role="dialog" aria-modal="true" aria-labelledby="bestaetigung-titel" onSubmit={bestaetigen}>
        <h2 id="bestaetigung-titel">{TITEL[anfrage.aktion]}</h2>
        <p>
          Gib zur Sicherheit einen aktuellen Code aus deiner Authenticator-App ein (oder einen Wiederherstellungscode). Die
          Bestätigung gilt danach 5 Minuten.
        </p>
        <label htmlFor="bestaetigung-code">Code</label>
        <input
          id="bestaetigung-code"
          ref={eingabeRef}
          autoComplete="one-time-code"
          inputMode="text"
          maxLength={32}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          readOnly={laeuft}
          required
        />
        {fehler && <p className="auth-error" role="alert">{fehler}</p>}
        <div className="actions">
          <button type="submit" className="button-primary" disabled={laeuft || code.trim().length < 6}>
            {laeuft ? "Wird geprüft …" : "Bestätigen"}
          </button>
          <button type="button" className="button-secondary" onClick={abbrechen} disabled={laeuft}>Abbrechen</button>
        </div>
      </form>
    </div>
  );
}
