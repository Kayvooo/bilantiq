import { useRef, useState } from "react";
import { ApiError } from "../auth/api";
import { ScanIcon } from "../../components/icons";
import { verkleinereBild } from "../../lib/bild";
import { uploadBeleg, type Receipt } from "./api";

interface Props {
  accessToken: string;
  onUploaded: (receipt: Receipt) => void;
}

export function ReceiptUpload({ accessToken, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const kameraRef = useRef<HTMLInputElement>(null);
  const lastFile = useRef<File | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const [duplicate, setDuplicate] = useState<Receipt | null>(null);

  async function doUpload(file: File, force: boolean) {
    setStatus("loading");
    setError("");
    setDuplicate(null);
    try {
      const receipt = await uploadBeleg(accessToken, await verkleinereBild(file), force);
      if (receipt.ist_duplikat && !force) {
        setDuplicate(receipt);
        setStatus("idle");
        return;
      }
      onUploaded(receipt);
      setStatus("idle");
      if (inputRef.current) inputRef.current.value = "";
      if (kameraRef.current) kameraRef.current.value = "";
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Upload ist fehlgeschlagen.");
    }
  }

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      lastFile.current = file;
      doUpload(file, false);
    }
  }

  return (
    <div className="panel upload-panel">
      <h2>Beleg hochladen</h2>
      <div className="upload-zone">
        <ScanIcon width={28} height={28} aria-hidden="true" />
        <label htmlFor="receipt-file">Foto, Scan, PDF oder E-Rechnung (XML) auswählen</label>
        <p className="auth-hint">Die lokale Texterkennung schlägt Betrag, Datum, Anbieter, USt-Satz und Kategorie vor. E-Rechnungen (XRechnung, ZUGFeRD) werden dagegen exakt aus den Rechnungsdaten gelesen.</p>
        <input id="receipt-file" ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf,application/xml,text/xml,.xml" onChange={handleChange} disabled={status === "loading"} />
        <input
          id="receipt-kamera" ref={kameraRef} type="file" accept="image/*" capture="environment" hidden
          onChange={handleChange} disabled={status === "loading"} aria-label="Foto aufnehmen"
        />
        <button type="button" className="auth-link kamera-button" onClick={() => kameraRef.current?.click()} disabled={status === "loading"}>
          Foto aufnehmen
        </button>
      </div>
      {status === "loading" && <p className="auth-hint">Wird hochgeladen und analysiert …</p>}
      {status === "error" && <p className="auth-error" role="alert">{error}</p>}
      {duplicate && (
        <div className="callout-dup">
          <p>Dieser Beleg wurde schon einmal hochgeladen (Beleg {duplicate.duplikat_von?.slice(0, 8)}…).</p>
          <button
            type="button"
            className="auth-link"
            onClick={() => lastFile.current && doUpload(lastFile.current, true)}
          >
            Trotzdem als neuen Beleg hochladen
          </button>
        </div>
      )}
    </div>
  );
}
