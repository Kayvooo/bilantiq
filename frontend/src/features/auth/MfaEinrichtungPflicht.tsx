import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, mfaSetupMitPreToken, mfaVerifyMitPreToken, type MfaSetupResponse } from "./api";
import { WiederherstellungscodesAnzeige } from "./WiederherstellungscodesAnzeige";

interface Props {
  /** Einrichtungs-Token aus der Anmeldung. Es oeffnet nur diese Einrichtung, keine Buchhaltungsdaten. */
  preAuthToken: string;
  /** Erst nach bestaetigtem Code UND gesicherten Wiederherstellungscodes. */
  onFertig: (accessToken: string) => void;
  onZurAnmeldung: () => void;
}

type Phase =
  | { name: "laedt" }
  | { name: "code"; setup: MfaSetupResponse }
  | { name: "codes"; accessToken: string; codes: string[] }
  | { name: "fehler"; meldung: string };

/** Pflicht-Einrichtung der Zwei-Faktor-Anmeldung (docs/specs/mfa-pflicht.md). Bis sie abgeschlossen ist, gibt es keine Sitzung. */
export function MfaEinrichtungPflicht({ preAuthToken, onFertig, onZurAnmeldung }: Props) {
  const [phase, setPhase] = useState<Phase>({ name: "laedt" });
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(false);

  // Nur EIN Setup-Aufruf je Einrichtungs-Token, auch wenn React den Effekt doppelt ausfuehrt (StrictMode): Zwei gleichzeitige
  // Erstaufrufe koennten serverseitig zwei verschiedene Secrets erzeugen, und gescannt wuerde das nicht gespeicherte.
  const setupAufruf = useRef<{ token: string; antwort: Promise<MfaSetupResponse> } | null>(null);

  useEffect(() => {
    let abgebrochen = false;
    if (setupAufruf.current?.token !== preAuthToken) {
      setupAufruf.current = { token: preAuthToken, antwort: mfaSetupMitPreToken(preAuthToken) };
    }
    setupAufruf.current.antwort
      .then((setup) => { if (!abgebrochen) setPhase({ name: "code", setup }); })
      .catch((err) => {
        if (!abgebrochen) {
          setPhase({ name: "fehler", meldung: err instanceof ApiError ? err.message : "Die Einrichtung konnte nicht gestartet werden." });
        }
      });
    return () => { abgebrochen = true; };
  }, [preAuthToken]);

  async function bestaetigen(ereignis: FormEvent) {
    ereignis.preventDefault();
    setLaeuft(true);
    setFehler("");
    try {
      const antwort = await mfaVerifyMitPreToken(preAuthToken, code.trim());
      if (antwort.wiederherstellungscodes?.length) {
        // Die Sitzung wird erst uebernommen, wenn die Codes gesichert sind: sie werden nie wieder angezeigt.
        setPhase({ name: "codes", accessToken: antwort.access_token, codes: antwort.wiederherstellungscodes });
      } else {
        onFertig(antwort.access_token);
      }
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Der Code konnte nicht bestätigt werden.");
      setLaeuft(false);
    }
  }

  if (phase.name === "laedt") {
    return <div className="auth-card" role="status">Einrichtung wird vorbereitet …</div>;
  }

  if (phase.name === "fehler") {
    return (
      <div className="auth-card">
        <h1>Einrichtung nicht möglich</h1>
        <p className="auth-error" role="alert">{phase.meldung}</p>
        <button type="button" onClick={onZurAnmeldung}>Zur Anmeldung</button>
      </div>
    );
  }

  if (phase.name === "codes") {
    const { accessToken, codes } = phase;
    return (
      <div className="auth-card">
        <h1>Wiederherstellungscodes sichern</h1>
        <WiederherstellungscodesAnzeige codes={codes} weiterLabel="Weiter zu Bilantiq" onWeiter={() => onFertig(accessToken)} />
      </div>
    );
  }

  return (
    <form className="auth-card" onSubmit={bestaetigen}>
      <h1>Zwei-Faktor-Anmeldung einrichten</h1>
      <p className="auth-hint">
        Für den Inhaber ist die Zwei-Faktor-Anmeldung Pflicht. In Bilantiq liegen Rechnungen, Belege und Geschäftszahlen; ein
        gestohlenes Passwort allein reicht dann nicht mehr. Du brauchst eine Authenticator-App (zum Beispiel Aegis oder Google Authenticator).
      </p>
      <ol className="auth-hint">
        <li>Trage das Secret in deiner Authenticator-App ein oder öffne den Link auf dem Gerät mit der App.</li>
        <li>Gib den aktuellen 6-stelligen Code ein.</li>
        <li>Sichere danach die Wiederherstellungscodes.</li>
      </ol>
      <div className="mfa-secret"><span className="mfa-secret-label">Secret</span><code>{phase.setup.secret}</code></div>
      <a className="auth-link" href={phase.setup.provisioning_uri}>In Authenticator-App öffnen</a>

      <label htmlFor="pflicht-mfa-code">6-stelliger Code</label>
      <input
        id="pflicht-mfa-code"
        autoComplete="one-time-code"
        inputMode="numeric"
        pattern="[0-9]{6}"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        readOnly={laeuft}
        required
        autoFocus
      />
      {fehler && <p className="auth-error" role="alert">{fehler}</p>}
      <button type="submit" disabled={laeuft}>{laeuft ? "Wird geprüft …" : "Code bestätigen"}</button>
      <button type="button" className="button-secondary" onClick={onZurAnmeldung} disabled={laeuft}>Abbrechen</button>
    </form>
  );
}
