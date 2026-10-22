import { useEffect, useRef, useState } from "react";
import { SCHLUESSEL, hinweisOffen } from "../../lib/mfaHinweis";

interface Props {
  onEinrichten: () => void;
}

/** Dringende Empfehlung für die Zwei-Faktor-Anmeldung. Sie ist optional, der Hinweis erscheint nach jeder
 * Anmeldung ohne MFA einmal am Dashboard, bis sie eingerichtet ist. */
export function MfaHinweis({ onEinrichten }: Props) {
  const [offen, setOffen] = useState(hinweisOffen);
  const einrichtenRef = useRef<HTMLButtonElement>(null);
  const spaeterRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (offen) einrichtenRef.current?.focus();
  }, [offen]);

  function schliessen() {
    try {
      sessionStorage.removeItem(SCHLUESSEL);
    } catch {
      // siehe markiereMfaHinweis
    }
    setOffen(false);
  }

  // Auf dem Dokument statt am Dialog: Nach einem Klick auf den Hintergrund liegt der Fokus auf dem body,
  // dort kämen weder Escape noch die Fokusfalle an, und Tab liefe in die verdeckte Seite dahinter.
  useEffect(() => {
    if (!offen) return;
    function beiTaste(ereignis: KeyboardEvent) {
      if (ereignis.key === "Escape") {
        ereignis.preventDefault();
        schliessen();
      } else if (ereignis.key === "Tab") {
        // Fokusfalle über die zwei Schaltflächen
        const erste = einrichtenRef.current;
        const letzte = spaeterRef.current;
        if (!erste || !letzte) return;
        const aktiv = document.activeElement;
        const imDialog = !!aktiv && !!erste.closest("[role=dialog]")?.contains(aktiv);
        if (ereignis.shiftKey && (aktiv === erste || !imDialog)) { ereignis.preventDefault(); letzte.focus(); }
        else if (!ereignis.shiftKey && (aktiv === letzte || !imDialog)) { ereignis.preventDefault(); erste.focus(); }
      }
    }
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offen]);

  if (!offen) return null;

  return (
    <div className="hinweis-overlay">
      <div className="hinweis-dialog" role="dialog" aria-modal="true" aria-labelledby="mfa-hinweis-titel">
        <h2 id="mfa-hinweis-titel">Schütze dein Konto mit Zwei-Faktor-Anmeldung</h2>
        <p>
          Wir empfehlen die Zwei-Faktor-Anmeldung dringend. In Bilantiq liegen deine Rechnungen, Belege und Geschäftszahlen.
          Ohne zweiten Faktor reicht ein gestohlenes oder erratenes Passwort, um darauf zuzugreifen.
        </p>
        <p className="auth-hint">Die Einrichtung dauert etwa eine Minute mit einer Authenticator-App wie Aegis oder Google Authenticator.</p>
        <div className="hinweis-aktionen">
          <button ref={einrichtenRef} type="button" className="button-primary" onClick={() => { schliessen(); onEinrichten(); }}>
            Jetzt einrichten
          </button>
          <button ref={spaeterRef} type="button" className="button-secondary" onClick={schliessen}>Später</button>
        </div>
      </div>
    </div>
  );
}
