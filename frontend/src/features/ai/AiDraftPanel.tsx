import { useState } from "react";
import { ApiError } from "../auth/api";
import type { InvoiceDraft } from "../invoices/api";
import type { QuoteDraft } from "../quotes/api";
import { createInvoiceDraftSuggestion, createQuoteDraftSuggestion } from "./api";

interface BaseProps {
  accessToken: string;
}

export function AiInvoiceDraftPanel({ accessToken, onGenerated }: BaseProps & { onGenerated: (draft: InvoiceDraft) => void }) {
  return <DraftPanel accessToken={accessToken} label="Rechnung" onGenerate={async (text) => onGenerated(await createInvoiceDraftSuggestion(accessToken, text))} />;
}

export function AiQuoteDraftPanel({ accessToken, onGenerated }: BaseProps & { onGenerated: (draft: QuoteDraft) => void }) {
  return <DraftPanel accessToken={accessToken} label="Angebot" onGenerate={async (text) => onGenerated(await createQuoteDraftSuggestion(accessToken, text))} />;
}

function DraftPanel({
  label,
  onGenerate,
}: {
  accessToken: string;
  label: "Rechnung" | "Angebot";
  onGenerate: (text: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function generate() {
    if (!text.trim()) return;
    setStatus("loading");
    setError("");
    try {
      await onGenerate(text.trim());
      setStatus("idle");
      setOpen(false);
      setText("");
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : `${label}-Entwurf konnte nicht erzeugt werden.`);
    }
  }

  if (!open) {
    return (
      <button type="button" className="auth-link" onClick={() => setOpen(true)}>
        {label} mit KI vorausfüllen
      </button>
    );
  }

  return (
    <div className="panel ai-draft-panel">
      <h2>{label} mit KI vorausfüllen</h2>
      <p className="auth-hint">Die KI füllt nur das normale Formular. Gespeichert wird erst nach deiner Prüfung.</p>
      <textarea
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={label === "Rechnung"
          ? "z.B. Rechnung an Müller GmbH: 10 Stunden Webentwicklung zu 90 EUR netto, 19 % USt."
          : "z.B. Angebot an Müller GmbH für Website-Relaunch: 2.500 EUR netto, 19 % USt."}
        maxLength={4000}
      />
      {status === "error" && <p className="auth-error" role="alert">{error}</p>}
      <div className="invoice-actions">
        <button type="button" disabled={status === "loading" || !text.trim()} onClick={generate}>
          {status === "loading" ? "Wird vorbereitet …" : "Formular vorausfüllen"}
        </button>
        <button type="button" className="auth-link" onClick={() => setOpen(false)} disabled={status === "loading"}>Abbrechen</button>
      </div>
    </div>
  );
}
