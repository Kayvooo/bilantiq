import { Fragment, useEffect, useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { AiTextComposer } from "../ai/AiTextComposer";
import { downloadBlob } from "./downloadBlob";
import { downloadMahnungPdf, listAlleMahnungen, sendeMahnung, type MahnungUebersicht } from "./api";

interface Props { accessToken: string; onBack: () => void }

const STUFE_TON: Record<number, string> = { 1: "neutral", 2: "warn", 3: "danger" };

export function MahnungenPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [mahnungen, setMahnungen] = useState<MahnungUebersicht[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openTextId, setOpenTextId] = useState<string | null>(null);

  async function load() {
    setStatus("loading");
    setError("");
    try {
      setMahnungen(await listAlleMahnungen(accessToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mahnungen konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleDownload(mahnung: MahnungUebersicht) {
    setBusyId(mahnung.id);
    setError("");
    try {
      downloadBlob(await downloadMahnungPdf(accessToken, mahnung.id), `Mahnung-${mahnung.rechnung_nummer}-Stufe${mahnung.stufe}.pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "PDF konnte nicht erstellt werden.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleSend(mahnung: MahnungUebersicht) {
    setBusyId(mahnung.id);
    setError("");
    try {
      await sendeMahnung(accessToken, mahnung.id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mahnung konnte nicht per E-Mail versendet werden.");
    } finally {
      setBusyId(null);
    }
  }

  if (status === "loading") return <PageState label="Mahnungen werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader title="Mahnungen" description="Alle bisher ausgestellten Zahlungserinnerungen und Mahnstufen." onBack={onBack} />

      {error && <p className="auth-error" role="alert">{error}</p>}

      {mahnungen.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Mahnungen</h2>
          <p className="auth-hint" style={{ margin: 0 }}>
            Mahnstufen legst du bei überfälligen Rechnungen direkt in „Rechnungen" an.
          </p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead>
              <tr><th>Rechnung</th><th>Kunde</th><th>Stufe</th><th>Neue Fälligkeit</th><th className="number">Betrag</th><th /></tr>
            </thead>
            <tbody>
              {mahnungen.map((mahnung) => (
                <Fragment key={mahnung.id}>
                <tr>
                  <td>{mahnung.rechnung_nummer || "—"}</td>
                  <td>{mahnung.kontakt_name}</td>
                  <td>
                    <span className={`status-pill status-pill--${STUFE_TON[mahnung.stufe] ?? "neutral"}`}>{mahnung.stufe_bezeichnung}</span>
                    {mahnung.versendet_am && <div className="auth-hint">Versendet am {formatDate(mahnung.versendet_am.slice(0, 10))}</div>}
                    {!mahnung.kontakt_email_vorhanden && <div className="auth-hint">Kein E-Mail-Versand: Beim Kontakt fehlt die E-Mail-Adresse.</div>}
                  </td>
                  <td>{formatDate(mahnung.neue_faelligkeit)}</td>
                  <td className="number">{formatMoney(mahnung.rechnung_brutto)}</td>
                  <td>
                    <button type="button" className="auth-link" disabled={busyId === mahnung.id} onClick={() => handleDownload(mahnung)}>
                      {busyId === mahnung.id ? "Wird erstellt …" : "PDF"}
                    </button>
                    <button
                      type="button"
                      className="auth-link"
                      disabled={busyId === mahnung.id || !mahnung.kontakt_email_vorhanden}
                      title={!mahnung.kontakt_email_vorhanden ? "Der Kontakt hat keine E-Mail-Adresse hinterlegt." : undefined}
                      onClick={() => handleSend(mahnung)}
                    >
                      Per E-Mail senden
                    </button>
                    <button
                      type="button"
                      className="auth-link"
                      disabled={!mahnung.kontakt_email_vorhanden}
                      onClick={() => setOpenTextId(openTextId === mahnung.id ? null : mahnung.id)}
                    >
                      KI-Text
                    </button>
                  </td>
                </tr>
                {openTextId === mahnung.id && (
                  <tr>
                    <td colSpan={6}>
                      <AiTextComposer
                        accessToken={accessToken}
                        art="mahnung"
                        objektId={mahnung.id}
                        onSend={async (text) => { await sendeMahnung(accessToken, mahnung.id, text); await load(); }}
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
      )}
    </div>
  );
}
