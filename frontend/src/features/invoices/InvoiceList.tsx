import { Fragment, useEffect, useState } from "react";
import { CheckIcon } from "../../components/icons";
import { StatusPill } from "../../components/StatusPill";
import { ApiError } from "../auth/api";
import { AiTextComposer } from "../ai/AiTextComposer";
import {
  createMahnung,
  downloadInvoicePdf,
  downloadMahnungPdf,
  downloadXRechnung,
  downloadZugferdPdf,
  finalizeInvoice,
  listMahnungen,
  markInvoicePaid,
  sendeRechnung,
  stornoInvoice,
  type Invoice,
  type Mahnung,
} from "./api";
import { downloadBlob } from "./downloadBlob";
import { formatDate, formatMoney } from "../../lib/format";

interface Props {
  accessToken: string;
  invoices: Invoice[];
  onChanged: () => void;
}

function MahnwesenPanel({ accessToken, invoice, onChanged }: { accessToken: string; invoice: Invoice; onChanged: () => void }) {
  const [mahnungen, setMahnungen] = useState<Mahnung[] | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setStatus("loading");
    try {
      setMahnungen(await listMahnungen(accessToken, invoice.id));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mahnungen konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoice.id]);

  async function handleCreate() {
    setBusy(true);
    setError("");
    try {
      await createMahnung(accessToken, invoice.id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mahnung konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="confirm-row">
      <strong>Mahnungen</strong>
      {status === "loading" && <p className="auth-hint">Wird geladen …</p>}
      {status === "error" && <p className="auth-error" role="alert">{error}</p>}
      {status === "ready" && mahnungen && mahnungen.length === 0 && <p className="auth-hint">Noch keine Mahnung erstellt.</p>}
      {status === "ready" && mahnungen && mahnungen.length > 0 && (
        <ul className="mahnungen-liste">
          {mahnungen.map((m) => (
            <li key={m.id}>
              {m.stufe_bezeichnung} — Gebühr {formatMoney(m.mahngebuehr, invoice.waehrung)}, neues Ziel {formatDate(m.neue_faelligkeit)}{" "}
              <button
                type="button"
                className="auth-link"
                onClick={async () => downloadBlob(await downloadMahnungPdf(accessToken, m.id), `${m.stufe_bezeichnung}-${invoice.nummer}.pdf`)}
              >
                PDF
              </button>
            </li>
          ))}
        </ul>
      )}
      {invoice.anzeige_status === "ueberfaellig" && (!mahnungen || mahnungen.length < 3) && (
        <button type="button" disabled={busy} onClick={handleCreate}>
          {busy ? "Wird erstellt …" : "Nächste Mahnstufe erstellen"}
        </button>
      )}
      {error && status !== "error" && <p className="auth-error" role="alert">{error}</p>}
      <button type="button" className="auth-link" onClick={onChanged}>Schließen</button>
    </div>
  );
}

export function InvoiceList({ accessToken, invoices, onChanged }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openMahnungId, setOpenMahnungId] = useState<string | null>(null);
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

  if (invoices.length === 0) {
    return (
      <div className="empty-state">
        <h2>Noch keine Rechnungen erstellt</h2>
        <ul>
          <li><CheckIcon width={18} height={18} /> Positionen, Steuersätze und Rabatte automatisch berechnet</li>
          <li><CheckIcon width={18} height={18} /> XRechnung und ZUGFeRD auf Knopfdruck</li>
          <li><CheckIcon width={18} height={18} /> Fortlaufende, lückenlose Rechnungsnummern nach GoBD</li>
        </ul>
        <p className="auth-hint" style={{ margin: 0 }}>Lege oben die erste Rechnung an.</p>
      </div>
    );
  }

  return (
    <div>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <div className="table-scroll">
      <table className="positions-table">
        <thead>
          <tr>
            <th>Nummer</th><th>Kunde</th><th>Status</th><th>Betrag</th><th>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <Fragment key={invoice.id}>
              <tr data-fokus-id={invoice.id}>
                <td>{invoice.nummer ?? "—"}</td>
                <td>{invoice.kontakt_name}</td>
                <td>
                  <StatusPill status={invoice.anzeige_status} />
                  {invoice.versendet_am && <div className="auth-hint">Versendet am {formatDate(invoice.versendet_am.slice(0, 10))}</div>}
                  {invoice.status === "final" && !invoice.kontakt_email_vorhanden && <div className="auth-hint">Kein E-Mail-Versand: Beim Kontakt fehlt die E-Mail-Adresse.</div>}
                </td>
                <td className="number">{formatMoney(invoice.brutto_gesamt, invoice.waehrung)}</td>
                <td className="invoice-actions">
                  {invoice.status === "entwurf" && (
                    <button
                      type="button"
                      disabled={busyId === invoice.id}
                      onClick={() => run(invoice.id, async () => { await finalizeInvoice(accessToken, invoice.id); onChanged(); })}
                    >
                      Finalisieren
                    </button>
                  )}
                  <button
                    type="button"
                    className="auth-link"
                    disabled={busyId === invoice.id}
                    onClick={() => run(invoice.id, async () => {
                      const blob = await downloadInvoicePdf(accessToken, invoice.id);
                      downloadBlob(blob, `${invoice.nummer ?? "entwurf"}.pdf`);
                    })}
                  >
                    PDF
                  </button>
                  <button
                    type="button"
                    className="auth-link"
                    disabled={busyId === invoice.id || invoice.status !== "final" || !invoice.kontakt_email_vorhanden}
                    title={
                      invoice.status !== "final"
                        ? "Nur finale Rechnungen koennen per E-Mail versendet werden."
                        : !invoice.kontakt_email_vorhanden
                        ? "Der Kontakt hat keine E-Mail-Adresse hinterlegt."
                        : undefined
                    }
                    onClick={() => run(invoice.id, async () => { await sendeRechnung(accessToken, invoice.id); onChanged(); })}
                  >
                    Per E-Mail senden
                  </button>
                  <button
                    type="button"
                    className="auth-link"
                    disabled={invoice.status !== "final" || !invoice.kontakt_email_vorhanden}
                    onClick={() => setOpenTextId(openTextId === invoice.id ? null : invoice.id)}
                  >
                    KI-Text
                  </button>
                  {invoice.status === "final" && invoice.e_rechnung_hinweis && (
                    <>
                      <button
                        type="button"
                        className="auth-link"
                        disabled={busyId === invoice.id}
                        onClick={() => run(invoice.id, async () => {
                          const blob = await downloadXRechnung(accessToken, invoice.id);
                          downloadBlob(blob, `${invoice.nummer}.xml`);
                          onChanged();
                        })}
                      >
                        XRechnung
                      </button>
                      <button
                        type="button"
                        className="auth-link"
                        disabled={busyId === invoice.id}
                        onClick={() => run(invoice.id, async () => {
                          const blob = await downloadZugferdPdf(accessToken, invoice.id);
                          downloadBlob(blob, `${invoice.nummer}-zugferd.pdf`);
                          onChanged();
                        })}
                      >
                        ZUGFeRD-PDF
                      </button>
                    </>
                  )}
                  {(invoice.anzeige_status === "final" || invoice.anzeige_status === "ueberfaellig") && (
                    <button
                      type="button"
                      className="auth-link"
                      disabled={busyId === invoice.id}
                      onClick={() => run(invoice.id, async () => { await markInvoicePaid(accessToken, invoice.id); onChanged(); })}
                    >
                      Als bezahlt markieren
                    </button>
                  )}
                  {invoice.status === "final" && (
                    <button
                      type="button"
                      className="auth-link"
                      onClick={() => setOpenMahnungId(openMahnungId === invoice.id ? null : invoice.id)}
                    >
                      Mahnwesen
                    </button>
                  )}
                  {invoice.status === "final" && (
                    <button
                      type="button"
                      className="auth-link danger"
                      disabled={busyId === invoice.id}
                      onClick={() => run(invoice.id, async () => { await stornoInvoice(accessToken, invoice.id); onChanged(); })}
                    >
                      Stornieren
                    </button>
                  )}
                </td>
              </tr>
              {openMahnungId === invoice.id && (
                <tr>
                  <td colSpan={5}>
                    <MahnwesenPanel accessToken={accessToken} invoice={invoice} onChanged={() => { setOpenMahnungId(null); onChanged(); }} />
                  </td>
                </tr>
              )}
              {openTextId === invoice.id && (
                <tr>
                  <td colSpan={5}>
                    <AiTextComposer
                      accessToken={accessToken}
                      art="rechnung"
                      objektId={invoice.id}
                      onSend={async (text) => { await sendeRechnung(accessToken, invoice.id, text); onChanged(); }}
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
