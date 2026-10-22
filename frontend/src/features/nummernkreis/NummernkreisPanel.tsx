import { useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../auth/api";
import { getNummernkreis, setzeNummernkreis, type Nummernkreis } from "./api";

interface Props {
  accessToken: string;
  istInhaber: boolean;
  /** Nur anzeigen, wenn Bilantiq sonst Nummern vergeben wuerde, die es im alten Programm schon gibt. */
  nurBeiKollision?: boolean;
  onGeaendert?: () => void;
}

function nummer(jahr: number, laufnummer: number): string {
  return `RE-${jahr}-${String(laufnummer).padStart(4, "0")}`;
}

/** Zeigt die naechste Rechnungsnummer und setzt den Nummernkreis fort (nur nach oben). Wer von einem anderen
 * Programm kommt, hat dort schon Nummern desselben Formats vergeben: eine doppelte Rechnungsnummer waere nach
 * § 14 UStG ein Fehler. */
export function NummernkreisPanel({ accessToken, istInhaber, nurBeiKollision = false, onGeaendert }: Props) {
  const [kreis, setKreis] = useState<Nummernkreis | null>(null);
  const [wert, setWert] = useState("");
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [arbeitet, setArbeitet] = useState(false);

  useEffect(() => {
    let aktiv = true;
    getNummernkreis(accessToken)
      .then((antwort) => { if (aktiv) { setKreis(antwort); setWert(String(antwort.mindestens)); } })
      .catch((err) => { if (aktiv) setFehler(err instanceof ApiError ? err.message : "Der Nummernkreis konnte nicht geladen werden."); });
    return () => { aktiv = false; };
  }, [accessToken]);

  async function setzen(naechste: number) {
    setArbeitet(true);
    setFehler("");
    setMeldung("");
    try {
      const antwort = await setzeNummernkreis(accessToken, naechste);
      setKreis(antwort);
      setWert(String(antwort.mindestens));
      setMeldung(`Die nächste Rechnung bekommt die Nummer ${antwort.naechste_rechnungsnummer}.`);
      onGeaendert?.();
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Der Nummernkreis konnte nicht gesetzt werden.");
    } finally {
      setArbeitet(false);
    }
  }

  function absenden(event: FormEvent) {
    event.preventDefault();
    const zahl = Number(wert);
    if (!wert.trim() || !Number.isInteger(zahl)) { setFehler("Bitte eine ganze Zahl eingeben."); return; }
    void setzen(zahl);
  }

  if (!kreis) return fehler ? <p className="auth-error" role="alert">{fehler}</p> : null;
  if (nurBeiKollision && !kreis.kollision && !meldung) return null;

  return (
    <div className="nummernkreis">
      <h3>Rechnungsnummern</h3>
      <p className="auth-hint">
        Die nächste Rechnung bekommt die Nummer <strong>{kreis.naechste_rechnungsnummer}</strong>.
        {kreis.hoechste_altsystem !== null && <> Im alten Programm gab es bis <strong>{nummer(kreis.jahr, kreis.hoechste_altsystem)}</strong>.</>}
      </p>
      {kreis.kollision && kreis.vorschlag !== null && (
        <div className="nummernkreis-warnung" role="alert">
          <p>
            Bilantiq würde Rechnungsnummern vergeben, die es im alten Programm schon gibt. Eine doppelte Nummer ist nach § 14 UStG nicht
            erlaubt, deshalb lässt sich die nächste Rechnung so nicht finalisieren. Setze die nächste Nummer hinter die letzte alte.
          </p>
          {istInhaber && (
            <button type="button" className="button-primary" disabled={arbeitet} onClick={() => void setzen(kreis.vorschlag!)}>
              Auf {nummer(kreis.jahr, kreis.vorschlag)} setzen
            </button>
          )}
        </div>
      )}
      {fehler && <p className="auth-error" role="alert">{fehler}</p>}
      {meldung && <p className="auth-hint" role="status">{meldung}</p>}
      {istInhaber ? (
        <form className="nummernkreis-formular" onSubmit={absenden} noValidate>
          <div>
            <label htmlFor="nummernkreis-wert">Nächste Laufnummer ({kreis.jahr})</label>
            <input id="nummernkreis-wert" type="number" inputMode="numeric" min={kreis.mindestens} max={999999} value={wert} onChange={(e) => setWert(e.target.value)} />
          </div>
          <button type="submit" disabled={arbeitet}>{arbeitet ? "Wird gesetzt …" : "Nummernkreis setzen"}</button>
        </form>
      ) : (
        <p className="auth-hint">Nur der Inhaber kann den Nummernkreis ändern.</p>
      )}
      <p className="auth-hint">
        Der Nummernkreis lässt sich nur erhöhen, nie senken. Die übersprungenen Nummern gehören dem alten Programm. Jede Änderung steht im
        Änderungsprotokoll.
      </p>
    </div>
  );
}
