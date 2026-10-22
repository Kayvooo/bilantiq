import { useRef, useState } from "react";
import { ApiError } from "../auth/api";
import { downloadBlob } from "../invoices/downloadBlob";
import { ladeExport, type ExportFormat, type ExportZiel } from "./api";

interface Props {
  accessToken: string;
  ziel: ExportZiel;
  istInhaber: boolean;
  onImportieren: () => void;
  onFehler: (meldung: string) => void;
}

/** Import und Export sind nur fuer den Inhaber freigegeben (wie der DSGVO-Export). Fuer
 * Mitglieder blendet sich die Leiste aus, statt einen 403 zu zeigen (siehe useIstInhaber). */
export function StammdatenAktionen({ accessToken, ziel, istInhaber, onImportieren, onFehler }: Props) {
  const [laedt, setLaedt] = useState<ExportFormat | null>(null);
  const menueRef = useRef<HTMLDetailsElement>(null);

  async function exportieren(format: ExportFormat) {
    setLaedt(format);
    try {
      const inhalt = await ladeExport(accessToken, ziel, format);
      downloadBlob(inhalt, `bilantiq-${ziel}-${new Date().toISOString().slice(0, 10)}.${format}`);
      if (menueRef.current) menueRef.current.open = false;
    } catch (err) {
      onFehler(err instanceof ApiError ? err.message : "Der Export ist fehlgeschlagen.");
    } finally {
      setLaedt(null);
    }
  }

  if (!istInhaber) return null;

  return (
    <div className="stammdaten-aktionen">
      <button type="button" className="auth-link" onClick={onImportieren}>Importieren</button>
      <details className="menue" ref={menueRef}>
        <summary className="auth-link">Exportieren</summary>
        <div className="menue-liste" role="menu">
          <button type="button" role="menuitem" onClick={() => exportieren("xlsx")} disabled={laedt !== null}>
            {laedt === "xlsx" ? "Wird erstellt …" : "Als Excel (.xlsx)"}
          </button>
          <button type="button" role="menuitem" onClick={() => exportieren("csv")} disabled={laedt !== null}>
            {laedt === "csv" ? "Wird erstellt …" : "Als CSV"}
          </button>
        </div>
      </details>
    </div>
  );
}
