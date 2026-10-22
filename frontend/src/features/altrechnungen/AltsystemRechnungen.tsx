import { Fragment, useEffect, useState, type FormEvent } from "react";
import { KeineListenTreffer, ListenWerkzeug } from "../../components/ListenWerkzeug";
import { PageState } from "../../components/PageState";
import { StatusPill } from "../../components/StatusPill";
import { formatDate, formatMoney } from "../../lib/format";
import { betragSuchtext } from "../../lib/suchtext";
import { useFokus } from "../../lib/useFokus";
import { useListenFilter } from "../../lib/useListenFilter";
import { ApiError } from "../auth/api";
import { downloadBlob } from "../invoices/downloadBlob";
import { NummernkreisPanel } from "../nummernkreis/NummernkreisPanel";
import { ImportAssistent } from "../stammdaten/ImportAssistent";
import { erfasseZahlung, ladeAltPdf, listeAltrechnungen, type Altrechnung } from "./api";
import { PdfZuordnung } from "./PdfZuordnung";

interface Props {
  accessToken: string;
  istInhaber: boolean;
  /** Rechnung, zu der die Suche gesprungen ist */
  fokusId?: string;
}

/** "1.234,56" (deutsch) und "1234.56" (Punkt als Komma) sind beide gueltig. Mit Komma gelten Punkte als Tausendertrenner. */
function betragFuerServer(text: string): string {
  const kompakt = text.trim().replace(/\s/g, "");
  return kompakt.includes(",") ? kompakt.replace(/\./g, "").replace(",", ".") : kompakt;
}

function heute(): string {
  const jetzt = new Date();
  return `${jetzt.getFullYear()}-${String(jetzt.getMonth() + 1).padStart(2, "0")}-${String(jetzt.getDate()).padStart(2, "0")}`;
}

/** Rechnungen aus dem frueheren Programm: Archiv mit offenen Posten. Was dort schon bezahlt war, zaehlt in keiner
 * Auswertung. Offene Rechnungen zaehlen als Forderung, und eine hier erfasste Zahlung geht ab dem Zahlungsdatum in
 * Einnahmen-Ueberschuss-Rechnung und Umsatzsteuer ein. */
export function AltsystemRechnungen({ accessToken, istInhaber, fokusId }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [fehler, setFehler] = useState("");
  const [liste, setListe] = useState<Altrechnung[]>([]);
  const [importOffen, setImportOffen] = useState(false);
  const [zahlungId, setZahlungId] = useState<string | null>(null);
  const [datum, setDatum] = useState(heute());
  const [betrag, setBetrag] = useState("");
  const [arbeitet, setArbeitet] = useState(false);
  const [meldung, setMeldung] = useState("");

  async function laden() {
    try {
      setListe((await listeAltrechnungen(accessToken)).eintraege);
      setStatus("ready");
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Die Rechnungen konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => {
    void laden();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const werkzeug = useListenFilter(liste, {
    suchtext: (a) => [a.nummer, a.kontakt_name, betragSuchtext(a.brutto)].join(" "),
    filter: [
      { id: "offen", label: "Offen", passt: (a) => a.status === "offen" },
      { id: "ueberfaellig", label: "Überfällig", passt: (a) => a.status === "ueberfaellig" },
      { id: "bezahlt", label: "Bezahlt", passt: (a) => a.status === "bezahlt" },
    ],
    sortierungen: [
      { id: "betrag-ab", label: "Betrag, höchster zuerst", vergleiche: (a, b) => Number(b.brutto) - Number(a.brutto) },
      { id: "offen-ab", label: "Offener Betrag, höchster zuerst", vergleiche: (a, b) => Number(b.offen) - Number(a.offen) },
      { id: "kunde", label: "Kunde A–Z", vergleiche: (a, b) => a.kontakt_name.localeCompare(b.kontakt_name, "de") },
    ],
  });
  useFokus(fokusId, status === "ready" && liste.some((a) => a.id === fokusId));

  function zahlungOeffnen(rechnung: Altrechnung) {
    setZahlungId(zahlungId === rechnung.id ? null : rechnung.id);
    setDatum(heute());
    setBetrag(rechnung.offen.replace(".", ","));
    setFehler("");
    setMeldung("");
  }

  async function zahlungErfassen(event: FormEvent, rechnung: Altrechnung) {
    event.preventDefault();
    setArbeitet(true);
    setFehler("");
    try {
      const aktualisiert = await erfasseZahlung(accessToken, rechnung.id, { datum, betrag: betragFuerServer(betrag) });
      setListe((alt) => alt.map((a) => (a.id === aktualisiert.id ? aktualisiert : a)));
      setZahlungId(null);
      setMeldung(`Zahlung auf ${rechnung.nummer} erfasst.`);
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Die Zahlung konnte nicht erfasst werden.");
    } finally {
      setArbeitet(false);
    }
  }

  async function pdfLaden(rechnung: Altrechnung) {
    setFehler("");
    try {
      downloadBlob(await ladeAltPdf(accessToken, rechnung.id), `${rechnung.nummer.replace(/[^\w.-]+/g, "_")}.pdf`);
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Das PDF konnte nicht geladen werden.");
    }
  }

  if (status === "loading") return <PageState label="Rechnungen aus dem alten Programm werden geladen …" />;
  if (status === "error") return <PageState label={fehler} error onRetry={laden} />;

  const importAssistent = importOffen && (
    <ImportAssistent
      accessToken={accessToken} ziel="rechnungen"
      onAbbrechen={() => setImportOffen(false)}
      onFertig={() => { setImportOffen(false); void laden(); }}
    />
  );

  if (liste.length === 0) {
    return (
      <>
        {importAssistent}
        {!importOffen && (
          <div className="empty-state">
            <h2>Noch keine Rechnungen aus einem alten Programm</h2>
            <p className="auth-hint" style={{ margin: 0 }}>
              Übernimm die Rechnungsliste aus deinem bisherigen Programm als Excel- oder CSV-Datei. Du siehst vorher genau, was passiert.
              Bereits bezahlte Rechnungen werden nur archiviert, offene zählen als Forderung.
            </p>
            {istInhaber
              ? <div className="actions"><button type="button" className="button-primary" onClick={() => setImportOffen(true)}>Rechnungsliste importieren</button></div>
              : <p className="auth-hint" style={{ margin: 0 }}>Das Importieren darf nur der Inhaber des Kontos.</p>}
          </div>
        )}
      </>
    );
  }

  const offeneSumme = liste.reduce((summe, a) => summe + Number(a.offen), 0);
  return (
    <>
      <p className="auth-hint">
        Diese Rechnungen stammen aus deinem alten Programm und bleiben unverändert. Was dort schon bezahlt war, zählt in keiner Auswertung.
        Offene Rechnungen zählen als Forderung ({formatMoney(offeneSumme.toFixed(2))}). Eine Zahlung, die du hier erfasst, geht ab dem
        Zahlungsdatum in Einnahmen-Überschuss-Rechnung und Umsatzsteuer ein und lässt sich nicht zurücknehmen.
      </p>
      {importAssistent}
      {istInhaber && !importOffen && (
        <div className="actions"><button type="button" className="auth-link" onClick={() => setImportOffen(true)}>Weitere Rechnungsliste importieren</button></div>
      )}
      {fehler && <p className="auth-error" role="alert">{fehler}</p>}
      {meldung && <p className="auth-hint" role="status">{meldung}</p>}

      <div className="panel"><NummernkreisPanel accessToken={accessToken} istInhaber={istInhaber} nurBeiKollision /></div>
      <PdfZuordnung accessToken={accessToken} ohnePdf={liste.filter((a) => !a.hat_pdf)} onGeaendert={() => void laden()} />

      <ListenWerkzeug steuerung={werkzeug} placeholder="Nummer, Kunde oder Betrag" ariaLabel="Rechnungen aus dem alten Programm durchsuchen" />
      {werkzeug.sichtbar.length === 0 ? <KeineListenTreffer onZuruecksetzen={werkzeug.zuruecksetzen} /> : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead>
              <tr><th>Nummer</th><th>Kunde</th><th>Datum</th><th>Fällig</th><th className="number">Brutto</th><th className="number">Offen</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {werkzeug.sichtbar.map((rechnung) => (
                <Fragment key={rechnung.id}>
                  <tr data-fokus-id={rechnung.id}>
                    <td>{rechnung.nummer}</td>
                    <td>{rechnung.kontakt_name}</td>
                    <td>{formatDate(rechnung.rechnungsdatum)}</td>
                    <td>{rechnung.faelligkeit ? formatDate(rechnung.faelligkeit) : "—"}</td>
                    <td className="number">{formatMoney(rechnung.brutto)}</td>
                    <td className="number">{Number(rechnung.offen) > 0 ? formatMoney(rechnung.offen) : "—"}</td>
                    <td>
                      <StatusPill status={rechnung.status} />
                      {rechnung.status === "bezahlt" && (
                        <div className="zelle-nebentext">{rechnung.bezahlt_im_altsystem ? "im alten Programm" : "in Bilantiq"}</div>
                      )}
                    </td>
                    <td>
                      <div className="actions">
                        {rechnung.hat_pdf
                          ? <button type="button" className="auth-link" onClick={() => void pdfLaden(rechnung)}>PDF</button>
                          : <span className="zelle-nebentext">kein PDF</span>}
                        {Number(rechnung.offen) > 0 && (
                          <button type="button" className="auth-link" onClick={() => zahlungOeffnen(rechnung)}>
                            {zahlungId === rechnung.id ? "Schließen" : "Zahlung erfassen"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {(zahlungId === rechnung.id || rechnung.zahlungen.length > 0) && (
                    <tr>
                      <td colSpan={8}>
                        {rechnung.zahlungen.length > 0 && (
                          <ul className="mahnungen-liste" aria-label={`Zahlungen auf ${rechnung.nummer}`}>
                            {rechnung.zahlungen.map((z) => (
                              <li key={z.id}>
                                {formatDate(z.datum)}: {formatMoney(z.betrag)} {z.quelle === "bankabgleich" ? "(Bankabgleich)" : "(erfasst)"}
                              </li>
                            ))}
                          </ul>
                        )}
                        {zahlungId === rechnung.id && (
                          <form className="confirm-row" onSubmit={(e) => void zahlungErfassen(e, rechnung)}>
                            <div className="field-row">
                              <div>
                                <label htmlFor={`zahl-datum-${rechnung.id}`}>Zahlungsdatum</label>
                                <input id={`zahl-datum-${rechnung.id}`} type="date" value={datum} max={heute()} required onChange={(e) => setDatum(e.target.value)} />
                              </div>
                              <div>
                                <label htmlFor={`zahl-betrag-${rechnung.id}`}>Betrag in Euro</label>
                                <input id={`zahl-betrag-${rechnung.id}`} inputMode="decimal" value={betrag} required onChange={(e) => setBetrag(e.target.value)} />
                              </div>
                            </div>
                            <p className="auth-hint">
                              Offen sind {formatMoney(rechnung.offen)}. Ein kleinerer Betrag ist eine Teilzahlung, der Rest bleibt offen.
                            </p>
                            <div className="actions">
                              <button type="submit" disabled={arbeitet}>{arbeitet ? "Wird erfasst …" : "Zahlung erfassen"}</button>
                            </div>
                          </form>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
