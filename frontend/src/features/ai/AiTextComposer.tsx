import { useState } from "react";
import { ApiError } from "../auth/api";
import { createTextSuggestion, type TextArt, type TextTon } from "./api";

interface Props {
  accessToken: string;
  art: TextArt;
  objektId: string;
  onSend: (text: string) => Promise<void>;
  onClose: () => void;
}

export function AiTextComposer({ accessToken, art, objektId, onSend, onClose }: Props) {
  const [ton, setTon] = useState<TextTon>("neutral");
  const [hinweis, setHinweis] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "generating" | "sending" | "error">("idle");
  const [error, setError] = useState("");

  async function generate() {
    setStatus("generating");
    setError("");
    try {
      const result = await createTextSuggestion(accessToken, {
        art,
        objekt_id: objektId,
        ton,
        ...(hinweis.trim() ? { hinweis: hinweis.trim() } : {}),
      });
      setText(result.text);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "KI-Text konnte nicht erzeugt werden.");
    }
  }

  async function send() {
    if (!text.trim()) return;
    setStatus("sending");
    setError("");
    try {
      await onSend(text.trim());
      onClose();
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "E-Mail konnte nicht versendet werden.");
    }
  }

  return (
    <div className="confirm-row ai-text-composer">
      <strong>KI-Textvorschlag</strong>
      <div className="field-row">
        <div>
          <label>Ton</label>
          <select value={ton} onChange={(e) => setTon(e.target.value as TextTon)}>
            <option value="freundlich">Freundlich</option>
            <option value="neutral">Neutral</option>
            <option value="bestimmt">Bestimmt</option>
          </select>
        </div>
        <div>
          <label>Zusätzlicher Hinweis</label>
          <input value={hinweis} onChange={(e) => setHinweis(e.target.value)} placeholder="optional" maxLength={1000} />
        </div>
      </div>
      <button type="button" className="auth-link" onClick={generate} disabled={status === "generating" || status === "sending"}>
        {status === "generating" ? "Text wird erzeugt …" : text ? "Neu formulieren" : "Text erzeugen"}
      </button>
      {text && (
        <>
          <label>Text vor Versand prüfen</label>
          <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          <button type="button" onClick={send} disabled={status === "sending"}>
            {status === "sending" ? "Wird versendet …" : "Mit diesem Text senden"}
          </button>
        </>
      )}
      {status === "error" && <p className="auth-error" role="alert">{error}</p>}
      <button type="button" className="auth-link" onClick={onClose} disabled={status === "sending"}>Schließen</button>
    </div>
  );
}
