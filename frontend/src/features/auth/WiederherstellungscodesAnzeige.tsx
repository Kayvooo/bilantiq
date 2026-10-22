import { useState } from "react";
import "./wiederherstellung.css";

interface Props {
  codes: string[];
  /** Beschriftung der Schaltfläche, die den Dialog schließt (erst nach der Bestätigung aktiv). */
  weiterLabel: string;
  onWeiter: () => void;
}

/** Zeigt die Wiederherstellungscodes GENAU EINMAL. Danach gibt es sie nirgends mehr (der Server speichert nur Hashes). */
export function WiederherstellungscodesAnzeige({ codes, weiterLabel, onWeiter }: Props) {
  const [gespeichert, setGespeichert] = useState(false);
  const [kopiert, setKopiert] = useState(false);

  const text = `Bilantiq-Wiederherstellungscodes\nJeder Code funktioniert genau einmal.\n\n${codes.join("\n")}\n`;

  async function kopieren() {
    try {
      await navigator.clipboard.writeText(text);
      setKopiert(true);
    } catch {
      setKopiert(false); // Zwischenablage nicht verfügbar: die Codes bleiben markierbar
    }
  }

  function herunterladen() {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "bilantiq-wiederherstellungscodes.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="recovery-warning" role="alert">
        <strong>Jetzt sicher aufbewahren.</strong> Diese {codes.length} Codes werden nur dieses eine Mal angezeigt. Mit einem
        Code kommst du in dein Konto, wenn du dein Handy oder deine Authenticator-App verlierst. Jeder Code funktioniert
        genau einmal. Bewahre sie getrennt vom Handy auf, zum Beispiel im Passwortmanager oder ausgedruckt.
      </div>
      <ul className="recovery-codes" aria-label="Wiederherstellungscodes">
        {codes.map((code) => <li key={code}>{code}</li>)}
      </ul>
      <div className="recovery-actions">
        <button type="button" className="button-secondary" onClick={kopieren}>{kopiert ? "Kopiert" : "Kopieren"}</button>
        <button type="button" className="button-secondary" onClick={herunterladen}>Als Textdatei speichern</button>
      </div>
      <label className="checkbox-row">
        <input type="checkbox" checked={gespeichert} onChange={(e) => setGespeichert(e.target.checked)} />
        Ich habe die Codes sicher gespeichert.
      </label>
      <div className="actions">
        <button type="button" className="button-primary" disabled={!gespeichert} onClick={onWeiter}>{weiterLabel}</button>
      </div>
    </div>
  );
}
