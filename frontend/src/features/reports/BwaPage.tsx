import { useEffect, useState } from "react";
import { ComplianceHinweis } from "../../components/ComplianceHinweis";
import { PageHeader } from "../../components/PageHeader";
import { ApiError } from "../auth/api";
import { formatMoney } from "../../lib/format";
import { getBwa, type Bwa } from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
}

export function BwaPage({ accessToken, onBack }: Props) {
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [bwa, setBwa] = useState<Bwa | null>(null);

  useEffect(() => {
    getBwa(accessToken, jahr)
      .then((result) => { setBwa(result); setStatus("ready"); })
      .catch((err) => { setError(err instanceof ApiError ? err.message : "BWA konnte nicht geladen werden."); setStatus("error"); });
  }, [accessToken, jahr]);

  const leer = bwa && bwa.erloes_posten.length === 0 && bwa.kosten_posten.length === 0;

  return (
    <div className="invoices-page">
      <PageHeader title="Betriebswirtschaftliche Auswertung" description="Vereinfachte Kategorien-Ergebnisrechnung, kein amtliches DATEV-BWA-Schema." onBack={onBack} />

      <ComplianceHinweis titel="SKR03-Konten: nicht steuerberatergeprüft">
        Die zugrunde liegenden SKR03-Kontonummern sind eine Annahme und wurden nicht mit einem
        Steuerberater abgestimmt. Vor der Übergabe an die Kanzlei bitte bestätigen lassen.
      </ComplianceHinweis>

      <div className="panel">
        <label htmlFor="bwa-jahr">Jahr</label>
        <select id="bwa-jahr" value={jahr} onChange={(e) => { setStatus("loading"); setJahr(Number(e.target.value)); }}>
          {[jahr + 1, jahr, jahr - 1, jahr - 2].map((j) => (<option key={j} value={j}>{j}</option>))}
        </select>
      </div>

      {status === "loading" && <div className="panel"><p>Wird berechnet …</p></div>}
      {status === "error" && <div className="panel"><p className="auth-error" role="alert">{error}</p></div>}

      {status === "ready" && bwa && (
        leer ? (
          <div className="empty-state">
            <h2>Noch keine Buchungen {jahr}</h2>
            <p className="auth-hint" style={{ margin: 0 }}>Bezahlte Rechnungen und gebuchte Ausgaben erscheinen hier nach Kategorie sortiert.</p>
          </div>
        ) : (
          <div className="panel euer-summary">
            <p className="section-title" style={{ marginTop: 0 }}>Erlöse</p>
            {bwa.erloes_posten.map((posten) => (
              <div className="euer-row" key={posten.konto}><span>{posten.bezeichnung}</span><strong>{formatMoney(posten.betrag)}</strong></div>
            ))}
            <div className="euer-row"><span>Erlöse gesamt</span><strong>{formatMoney(bwa.erloese_gesamt)}</strong></div>

            <p className="section-title">Kosten</p>
            {bwa.kosten_posten.map((posten) => (
              <div className="euer-row" key={posten.konto}><span>{posten.bezeichnung}</span><strong>−{formatMoney(posten.betrag)}</strong></div>
            ))}
            <div className="euer-row"><span>Kosten gesamt</span><strong>−{formatMoney(bwa.kosten_gesamt)}</strong></div>

            <div className="euer-row euer-total"><span>Vorläufiges Ergebnis</span><strong>{formatMoney(bwa.vorlaeufiges_ergebnis)}</strong></div>
            <p className="hinweis">{bwa.hinweis}</p>
          </div>
        )
      )}
    </div>
  );
}
