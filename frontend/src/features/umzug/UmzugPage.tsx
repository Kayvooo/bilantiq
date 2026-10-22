import { useEffect, useState } from "react";
import { CheckIcon } from "../../components/icons";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { useIstInhaber } from "../../lib/useIstInhaber";
import { ApiError } from "../auth/api";
import { NummernkreisPanel } from "../nummernkreis/NummernkreisPanel";
import { getUmzug, type Umzug, type UmzugSchritt } from "./api";

export interface UmzugZiel {
  step: string;
  aktion?: "neu" | "import";
  ansicht?: "altsystem";
}

interface Props {
  accessToken: string;
  onBack: () => void;
  onOpen: (ziel: UmzugZiel) => void;
}

const STATUS_PILL: Partial<Record<UmzugSchritt["status"], string>> = { nicht_noetig: "Nicht nötig", info: "Zur Info" };

/** Checkliste fuer den Wechsel von einem anderen Programm. Der Stand wird aus den Daten abgeleitet (Importe,
 * Nummernkreis, Bank), es gibt nichts, was veralten koennte. */
export function UmzugPage({ accessToken, onBack, onOpen }: Props) {
  const istInhaber = useIstInhaber(accessToken);
  const [stand, setStand] = useState<Umzug | null>(null);
  const [fehler, setFehler] = useState("");
  const [versuch, setVersuch] = useState(0);
  const [kreisOffen, setKreisOffen] = useState(false);

  useEffect(() => {
    let aktiv = true;
    getUmzug(accessToken)
      .then((antwort) => { if (aktiv) setStand(antwort); })
      .catch((err) => { if (aktiv) setFehler(err instanceof ApiError ? err.message : "Der Umzugsassistent konnte nicht geladen werden."); });
    return () => { aktiv = false; };
  }, [accessToken, versuch]);

  if (fehler) return <PageState label={fehler} error onRetry={() => { setFehler(""); setVersuch((n) => n + 1); }} />;
  if (!stand) return <PageState label="Umzugsassistent wird geladen …" />;

  const prozent = stand.gesamt ? Math.round((stand.erledigt / stand.gesamt) * 100) : 100;
  const naechster = stand.schritte.find((s) => s.status === "offen" && !s.optional);

  return (
    <div className="invoices-page">
      <PageHeader
        title="Datenumzug" description="Wechsle von einem anderen Programm zu Bilantiq: Kontakte, Produkte und Rechnungen mitnehmen." onBack={onBack}
      />

      <div className="panel fortschritt">
        <div className="fortschritt-kopf">
          <strong>{stand.erledigt} von {stand.gesamt} erledigt</strong>
          <span className="auth-hint">{prozent} %</span>
        </div>
        <div className="fortschritt-balken" role="progressbar" aria-valuenow={prozent} aria-valuemin={0} aria-valuemax={100} aria-label="Fortschritt">
          <div className="fortschritt-fuellung" style={{ width: `${prozent}%` }} />
        </div>
        <p className="auth-hint" style={{ margin: 0 }}>
          Du musst nicht alles übernehmen. Die Schritte lassen sich in beliebiger Reihenfolge erledigen, und was du importierst, siehst du vorher in
          einem Probelauf. Anleitungen für einzelne Programme gibt es hier nicht, weil sich deren Menüs ändern.
        </p>
      </div>

      <ol className="schritte-liste">
        {stand.schritte.map((schritt) => {
          const erledigt = schritt.status === "erledigt";
          const istNaechster = schritt === naechster;
          const gesperrt = schritt.nur_inhaber && !istInhaber;
          const istKreis = schritt.id === "nummernkreis";
          return (
            <li key={schritt.id} className={`schritt${erledigt ? " schritt--erledigt" : ""}${istNaechster ? " schritt--naechster" : ""}${schritt.status === "nicht_noetig" ? " schritt--ruhend" : ""}`}>
              <span className="schritt-kreis" aria-hidden="true">{erledigt && <CheckIcon width={16} height={16} />}</span>
              <div className="schritt-text">
                <div className="schritt-titel">
                  {schritt.titel}
                  {schritt.optional && <span className="status-pill status-pill--neutral">Optional</span>}
                  {STATUS_PILL[schritt.status] && <span className="status-pill status-pill--neutral">{STATUS_PILL[schritt.status]}</span>}
                  {istNaechster && <span className="status-pill status-pill--ok">Nächster Schritt</span>}
                  {schritt.hinweis && !erledigt && <span className="status-pill status-pill--warn">{schritt.hinweis}</span>}
                </div>
                <p className="auth-hint" style={{ margin: 0 }}>{schritt.beschreibung}</p>
                {schritt.detail && <p className="schritt-detail">{schritt.detail}</p>}
                {gesperrt && schritt.status !== "erledigt" && <p className="auth-hint" style={{ margin: 0 }}>Das darf nur der Inhaber des Kontos.</p>}
              </div>
              {(schritt.ziel || istKreis) && schritt.status !== "nicht_noetig" && (
                <button
                  type="button" className={istNaechster ? "button-primary" : "auth-link"} disabled={gesperrt && !istKreis}
                  onClick={() => (istKreis ? setKreisOffen((offen) => !offen) : onOpen({ step: schritt.ziel!, aktion: schritt.aktion ?? undefined, ansicht: schritt.ansicht ?? undefined }))}
                  aria-label={`${schritt.titel}: ${erledigt ? "ansehen" : "öffnen"}`}
                  aria-expanded={istKreis ? kreisOffen : undefined}
                >
                  {istKreis ? (kreisOffen ? "Schließen" : "Öffnen") : erledigt ? "Ansehen" : "Öffnen"}
                </button>
              )}
              {istKreis && kreisOffen && (
                <div className="schritt-panel">
                  <NummernkreisPanel accessToken={accessToken} istInhaber={istInhaber} onGeaendert={() => setVersuch((n) => n + 1)} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
