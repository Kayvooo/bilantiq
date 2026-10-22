import { useEffect, useState } from "react";
import { ApiError } from "../auth/api";
import { PageHeader } from "../../components/PageHeader";
import { formatMoney } from "../../lib/format";
import { getUstva, type Ustva } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

const MONATSNAMEN = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

export function UstvaPage({ accessToken, onBack }: Props) {
  const heute = new Date();
  const [jahr, setJahr] = useState(heute.getFullYear());
  const [zeitraumTyp, setZeitraumTyp] = useState<"monat" | "quartal">("monat");
  const [periode, setPeriode] = useState(heute.getMonth() + 1);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [ustva, setUstva] = useState<Ustva | null>(null);

  useEffect(() => {
    getUstva(accessToken, jahr, zeitraumTyp, periode)
      .then((result) => { setUstva(result); setStatus("ready"); })
      .catch((err) => { setError(err instanceof ApiError ? err.message : "UStVA konnte nicht berechnet werden."); setStatus("error"); });
  }, [accessToken, jahr, zeitraumTyp, periode]);

  function handleZeitraumTypChange(next: "monat" | "quartal") {
    setStatus("loading");
    setZeitraumTyp(next);
    setPeriode(next === "monat" ? heute.getMonth() + 1 : Math.floor(heute.getMonth() / 3) + 1);
  }

  const periodenOptionen = zeitraumTyp === "monat"
    ? MONATSNAMEN.map((name, i) => ({ value: i + 1, label: name }))
    : [1, 2, 3, 4].map((q) => ({ value: q, label: `${q}. Quartal` }));

  return (
    <div className="invoices-page">
      <PageHeader title="Umsatzsteuervoranmeldung" description="Umsätze und Vorsteuer für den gewählten Meldezeitraum vorbereiten." onBack={onBack} />

      <div className="panel">
        <div className="field-row">
          <div>
            <label htmlFor="ustva-typ">Zeitraum</label>
            <select id="ustva-typ" value={zeitraumTyp} onChange={(e) => handleZeitraumTypChange(e.target.value as "monat" | "quartal")}>
              <option value="monat">Monatlich</option>
              <option value="quartal">Quartalsweise</option>
            </select>
          </div>
          <div>
            <label htmlFor="ustva-periode">{zeitraumTyp === "monat" ? "Monat" : "Quartal"}</label>
            <select id="ustva-periode" value={periode} onChange={(e) => { setStatus("loading"); setPeriode(Number(e.target.value)); }}>
              {periodenOptionen.map((p) => (<option key={p.value} value={p.value}>{p.label}</option>))}
            </select>
          </div>
          <div>
            <label htmlFor="ustva-jahr">Jahr</label>
            <select id="ustva-jahr" value={jahr} onChange={(e) => { setStatus("loading"); setJahr(Number(e.target.value)); }}>
              {[jahr + 1, jahr, jahr - 1].map((j) => (<option key={j} value={j}>{j}</option>))}
            </select>
          </div>
        </div>
      </div>

      {status === "loading" && <div className="panel"><p>Wird berechnet …</p></div>}
      {status === "error" && <div className="panel"><p className="auth-error" role="alert">{error}</p></div>}

      {status === "ready" && ustva && (
        <div className="panel euer-summary">
          <div className="euer-row"><span>Umsatz 19% (netto)</span><span>{formatMoney(ustva.umsatz_19_netto)}</span></div>
          <div className="euer-row muted"><span>Umsatzsteuer 19%</span><span>{formatMoney(ustva.umsatzsteuer_19)}</span></div>
          <div className="euer-row"><span>Umsatz 7% (netto)</span><span>{formatMoney(ustva.umsatz_7_netto)}</span></div>
          <div className="euer-row muted"><span>Umsatzsteuer 7%</span><span>{formatMoney(ustva.umsatzsteuer_7)}</span></div>
          {Number(ustva.umsatz_sonstige_netto) !== 0 && (
            <div className="euer-row muted"><span>Sonstige Umsätze (netto, z. B. 0 % / Sonderfälle)</span><span>{formatMoney(ustva.umsatz_sonstige_netto)}</span></div>
          )}
          <div className="euer-row"><span>Umsatzsteuer gesamt</span><span>{formatMoney(ustva.umsatzsteuer_gesamt)}</span></div>
          <div className="euer-row"><span>Abziehbare Vorsteuer</span><span>−{formatMoney(ustva.vorsteuer_gesamt)}</span></div>
          <div className="euer-row euer-total">
            <span>{Number(ustva.zahllast) >= 0 ? "Zahllast" : "Erstattung"}</span>
            <strong>{formatMoney(Math.abs(Number(ustva.zahllast)).toFixed(2))}</strong>
          </div>
          <div className="euer-row muted"><span>{ustva.anzahl_rechnungen} bezahlte Rechnung(en), {ustva.anzahl_ausgaben} Beleg(e) im Zeitraum</span></div>
          <p className="hinweis">{ustva.hinweis}</p>
        </div>
      )}
    </div>
  );
}
