import { Fragment, useState } from "react";
import { CheckIcon } from "../../components/icons";
import { StatusPill } from "../../components/StatusPill";
import { ApiError } from "../auth/api";
import { AiTextComposer } from "../ai/AiTextComposer";
import { downloadBlob } from "../invoices/downloadBlob";
import { acceptQuote, convertQuoteToInvoice, downloadQuotePdf, rejectQuote, sendQuote, sendeAngebot, type Quote } from "./api";
import { formatDate, formatMoney } from "../../lib/format";

interface Props {
  accessToken: string;
  quotes: Quote[];
  onChanged: () => void;
}

export function QuoteList({ accessToken, quotes, onChanged }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [openTextId, setOpenTextId] = useState<string | null>(null);

  async function run(id: string, action: () => Promise<void>) {
    setBusyId(id);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion ist fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  if (quotes.length === 0) {
    return (
      <div className="empty-state">
        <h2>Noch keine Angebote erstellt</h2>
        <ul>
          <li><CheckIcon width={18} height={18} /> Vom Angebot direkt zur Rechnung, ohne Doppeleingabe</li>
          <li><CheckIcon width={18} height={18} /> Status im Blick: versendet, angenommen, abgelehnt</li>
        </ul>
        <p className="auth-hint" style={{ margin: 0 }}>Lege oben das erste Angebot an.</p>
      </div>
    );
  }

  return (
    <div>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <div className="table-scroll">
      <table className="positions-table">
        <thead><tr><th>Nummer</th><th>Status</th><th>Gültig bis</th><th>Betrag</th><th>Aktionen</th></tr></thead>
        <tbody>
          {quotes.map((quote) => (
            <Fragment key={quote.id}>
            <tr data-fokus-id={quote.id}>
              <td>{quote.nummer ?? "—"}</td>
              <td>
                <StatusPill status={quote.anzeige_status} />
                {quote.email_versendet_am && <div className="auth-hint">Versendet am {formatDate(quote.email_versendet_am.slice(0, 10))}</div>}
                {quote.status !== "entwurf" && !quote.kontakt_email_vorhanden && <div className="auth-hint">Kein E-Mail-Versand: Beim Kontakt fehlt die E-Mail-Adresse.</div>}
              </td>
              <td>{formatDate(quote.gueltig_bis)}</td>
              <td className="number">{formatMoney(quote.brutto_gesamt, quote.waehrung)}</td>
              <td className="invoice-actions">
                {quote.status === "entwurf" && (
                  <button type="button" disabled={busyId === quote.id} onClick={() => run(quote.id, async () => { await sendQuote(accessToken, quote.id); onChanged(); })}>
                    Versenden
                  </button>
                )}
                <button
                  type="button"
                  className="auth-link"
                  disabled={busyId === quote.id || quote.status === "entwurf" || !quote.kontakt_email_vorhanden}
                  title={
                    quote.status === "entwurf"
                      ? "Entwuerfe koennen nicht per E-Mail versendet werden -- zuerst 'Versenden' waehlen."
                      : !quote.kontakt_email_vorhanden
                      ? "Der Kontakt hat keine E-Mail-Adresse hinterlegt."
                      : undefined
                  }
                  onClick={() => run(quote.id, async () => { await sendeAngebot(accessToken, quote.id); onChanged(); })}
                >
                  Per E-Mail senden
                </button>
                <button
                  type="button"
                  className="auth-link"
                  disabled={quote.status === "entwurf" || !quote.kontakt_email_vorhanden}
                  onClick={() => setOpenTextId(openTextId === quote.id ? null : quote.id)}
                >
                  KI-Text
                </button>
                {quote.anzeige_status === "versendet" && (
                  <>
                    <button type="button" className="auth-link" disabled={busyId === quote.id} onClick={() => run(quote.id, async () => { await acceptQuote(accessToken, quote.id); onChanged(); })}>
                      Annehmen
                    </button>
                    <button type="button" className="auth-link danger" disabled={busyId === quote.id} onClick={() => run(quote.id, async () => { await rejectQuote(accessToken, quote.id); onChanged(); })}>
                      Ablehnen
                    </button>
                  </>
                )}
                {quote.status === "angenommen" && !quote.umgewandelt_in_invoice_id && (
                  <button type="button" disabled={busyId === quote.id} onClick={() => run(quote.id, async () => { await convertQuoteToInvoice(accessToken, quote.id); onChanged(); })}>
                    In Rechnung umwandeln
                  </button>
                )}
                {quote.umgewandelt_in_invoice_id && <span className="auth-hint">Rechnung erstellt</span>}
                <button
                  type="button"
                  className="auth-link"
                  disabled={busyId === quote.id}
                  onClick={() => run(quote.id, async () => {
                    const blob = await downloadQuotePdf(accessToken, quote.id);
                    downloadBlob(blob, `${quote.nummer ?? "angebot-entwurf"}.pdf`);
                  })}
                >
                  PDF
                </button>
              </td>
            </tr>
            {openTextId === quote.id && (
              <tr>
                <td colSpan={5}>
                  <AiTextComposer
                    accessToken={accessToken}
                    art="angebot"
                    objektId={quote.id}
                    onSend={async (text) => { await sendeAngebot(accessToken, quote.id, text); onChanged(); }}
                    onClose={() => setOpenTextId(null)}
                  />
                </td>
              </tr>
            )}
            </Fragment>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
