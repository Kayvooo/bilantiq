import { useEffect, useState } from "react";
import { CheckIcon } from "../../components/icons";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { ApiError } from "../auth/api";
import { getErsteSchritte, type ErsteSchritte } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
  onOpen: (ziel: string) => void;
}

export function ErsteSchrittePage({ accessToken, onBack, onOpen }: Props) {
  const [stand, setStand] = useState<ErsteSchritte | null>(null);
  const [error, setError] = useState("");
  const [versuch, setVersuch] = useState(0);

  useEffect(() => {
    let aktiv = true;
    getErsteSchritte(accessToken)
      .then((antwort) => aktiv && setStand(antwort))
      .catch((err) => aktiv && setError(err instanceof ApiError ? err.message : "Die Checkliste konnte nicht geladen werden."));
    return () => { aktiv = false; };
  }, [accessToken, versuch]);

  if (error) return <PageState label={error} error onRetry={() => { setError(""); setVersuch((n) => n + 1); }} />;
  if (!stand) return <PageState label="Checkliste wird geladen …" />;

  const prozent = Math.round((stand.erledigt / stand.gesamt) * 100);
  const naechster = stand.schritte.find((schritt) => !schritt.erledigt && !schritt.optional);
  const alleFertig = !naechster;

  return (
    <div className="invoices-page">
      <PageHeader title="Erste Schritte" description="In wenigen Schritten ist dein Konto startklar." onBack={onBack} />

      <div className="panel fortschritt">
        <div className="fortschritt-kopf">
          <strong>{alleFertig ? "Alles eingerichtet" : `${stand.erledigt} von ${stand.gesamt} erledigt`}</strong>
          <span className="auth-hint">{prozent} %</span>
        </div>
        <div className="fortschritt-balken" role="progressbar" aria-valuenow={prozent} aria-valuemin={0} aria-valuemax={100} aria-label="Fortschritt">
          <div className="fortschritt-fuellung" style={{ width: `${prozent}%` }} />
        </div>
        {alleFertig && <p className="auth-hint" style={{ margin: 0 }}>Die Pflichtschritte sind erledigt. Alles Weitere findest du in der Navigation.</p>}
      </div>

      <ol className="schritte-liste">
        {stand.schritte.map((schritt) => {
          const istNaechster = schritt === naechster;
          return (
            <li key={schritt.id} className={`schritt${schritt.erledigt ? " schritt--erledigt" : ""}${istNaechster ? " schritt--naechster" : ""}`}>
              <span className="schritt-kreis" aria-hidden="true">{schritt.erledigt && <CheckIcon width={16} height={16} />}</span>
              <div className="schritt-text">
                <div className="schritt-titel">
                  {schritt.titel}
                  {schritt.optional && <span className="status-pill status-pill--neutral">Optional</span>}
                  {istNaechster && <span className="status-pill status-pill--ok">Nächster Schritt</span>}
                  {schritt.hinweis && !schritt.erledigt && <span className="status-pill status-pill--warn">{schritt.hinweis}</span>}
                </div>
                <p className="auth-hint" style={{ margin: 0 }}>{schritt.beschreibung}</p>
              </div>
              <button
                type="button"
                className={istNaechster ? "button-primary" : "auth-link"}
                onClick={() => onOpen(schritt.ziel)}
                aria-label={`${schritt.titel}: ${schritt.erledigt ? "ansehen" : "öffnen"}`}
              >
                {schritt.erledigt ? "Ansehen" : "Öffnen"}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
