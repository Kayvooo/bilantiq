import { useState } from "react";
import { MfaChallenge } from "./MfaChallenge";
import { MfaWiederherstellungscodeForm } from "./MfaWiederherstellungscodeForm";
import "./wiederherstellung.css";

interface Props {
  preAuthToken: string;
  onVerified: (accessToken: string) => void;
}

/** Zweiter Anmeldeschritt: Code aus der Authenticator-App oder Wiederherstellungscode (Gerät verloren). */
export function MfaAnmeldung({ preAuthToken, onVerified }: Props) {
  const [mitWiederherstellung, setMitWiederherstellung] = useState(false);

  if (mitWiederherstellung) {
    return <MfaWiederherstellungscodeForm preAuthToken={preAuthToken} onVerified={onVerified} onZurueck={() => setMitWiederherstellung(false)} />;
  }
  return (
    <>
      <MfaChallenge preAuthToken={preAuthToken} onVerified={onVerified} />
      <div className="auth-alt">
        <button type="button" className="auth-link" onClick={() => setMitWiederherstellung(true)}>
          Kein Zugriff auf die Authenticator-App? Wiederherstellungscode verwenden
        </button>
      </div>
    </>
  );
}
