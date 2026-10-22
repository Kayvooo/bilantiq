import { useEffect, useState } from "react";
import { downloadBlob } from "../invoices/downloadBlob";
import { ApiError } from "../auth/api";
import { PageHeader } from "../../components/PageHeader";
import { formatMoney } from "../../lib/format";
import { downloadDatevExport, getEuer, type Euer } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

export function EuerPage({ accessToken, onBack }: Props) {
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [euer, setEuer] = useState<Euer | null>(null);
  const [exportStatus, setExportStatus] = useState<"idle" | "loading" | "error">("idle");
  const [exportError, setExportError] = useState("");

  async function handleDatevExport() {
    setExportStatus("loading");
    setExportError("");
    try {
      const blob = await downloadDatevExport(accessToken, jahr);
      downloadBlob(blob, `EXTF_Buchungsstapel_${jahr}.csv`);
      setExportStatus("idle");
    } catch (err) {
      setExportStatus("error");
      setExportError(err instanceof ApiError ? err.message : "Export ist fehlgeschlagen.");
    }
  }

  useEffect(() => {
    getEuer(accessToken, jahr)
      .then((result) => { setEuer(result); setStatus("ready"); })
      .catch((err) => { setError(err instanceof ApiError ? err.message : "EÜR konnte nicht geladen werden."); setStatus("error"); });
  }, [accessToken, jahr]);

  return (
    <div className="invoices-page">
      <PageHeader title="Einnahmen-Überschuss-Rechnung" description="Bezahlte Einnahmen und gebuchte Ausgaben nach dem Zufluss-Abfluss-Prinzip." onBack={onBack} />

      <div className="panel">
        <label htmlFor="euer-jahr">Jahr</label>
        <select id="euer-jahr" value={jahr} onChange={(e) => { setStatus("loading"); setJahr(Number(e.target.value)); }}>
          {[jahr + 1, jahr, jahr - 1, jahr - 2].map((j) => (<option key={j} value={j}>{j}</option>))}
        </select>
      </div>

      {status === "loading" && <div className="panel"><p>Wird berechnet …</p></div>}
      {status === "error" && <div className="panel"><p className="auth-error" role="alert">{error}</p></div>}

      {status === "ready" && euer && (
        <div className="panel euer-summary">
          <div className="euer-row"><span>Betriebseinnahmen (netto)</span><strong>{formatMoney(euer.betriebseinnahmen_netto)}</strong></div>
          <div className="euer-row muted"><span>{euer.anzahl_einnahmen} bezahlte Rechnung(en) im Zeitraum</span></div>
          <div className="euer-row"><span>Betriebsausgaben (netto)</span><strong>−{formatMoney(euer.betriebsausgaben_netto)}</strong></div>
          <div className="euer-row muted"><span>{euer.anzahl_ausgaben} gebuchte Beleg(e) im Zeitraum</span></div>
          <div className="euer-row euer-total"><span>Überschuss</span><strong>{formatMoney(euer.ueberschuss_netto)}</strong></div>
          <div className="euer-row muted"><span>Noch offene Forderungen (brutto, nicht Teil der EÜR)</span><span>{formatMoney(euer.offene_forderungen_brutto)}</span></div>
          <p className="hinweis">{euer.hinweis}</p>
        </div>
      )}

      <div className="panel">
        <h2>DATEV-Export</h2>
        <p className="auth-hint">
          Buchungsstapel-CSV für den Steuerberater/DATEV — strukturell nach dem gängigen EXTF-Format,
          aber noch nicht gegen einen echten DATEV-Import getestet. Die verwendeten SKR03-Konten sind
          eine nicht steuerberatergeprüfte Annahme. Vor dem ersten echten Einsatz mit dem
          Steuerberater probeweise importieren und die Kontenzuordnung bestätigen lassen.
        </p>
        {exportStatus === "error" && <p className="auth-error" role="alert">{exportError}</p>}
        <button type="button" onClick={handleDatevExport} disabled={exportStatus === "loading"}>
          {exportStatus === "loading" ? "Wird erstellt …" : `Buchungsstapel ${jahr} herunterladen`}
        </button>
      </div>
    </div>
  );
}
