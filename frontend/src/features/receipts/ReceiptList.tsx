import { Fragment, useEffect, useState } from "react";
import { CheckIcon } from "../../components/icons";
import { StatusPill } from "../../components/StatusPill";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { bestaetigeBeleg, deleteBeleg, fetchBelegDatei, ladeLernvorschlag, type Receipt, type Steueranteil } from "./api";

interface Props {
  accessToken: string;
  belege: Receipt[];
  onChanged: () => void;
}

function FieldCell({ field, art }: { field: Receipt["betrag"]; art?: "geld" | "datum" }) {
  if (field.unklar) return <span className="tag-unklar">[UNKLAR]</span>;
  if (field.wert && art === "geld") return <span>{formatMoney(field.wert)}</span>;
  if (field.wert && art === "datum") return <span>{formatDate(field.wert)}</span>;
  return <span>{field.wert}</span>;
}

function ReceiptPreview({ accessToken, receipt }: { accessToken: string; receipt: Receipt }) {
  const receiptId = receipt.id;
  const [url, setUrl] = useState<string | null>(null);
  const [mime, setMime] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    fetchBelegDatei(accessToken, receiptId)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setMime(blob.type);
        setUrl(objectUrl);
      })
      .catch((err) => {
        if (active) setError(err instanceof ApiError ? err.message : "Originalbeleg konnte nicht geladen werden.");
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [accessToken, receiptId]);

  if (error) return <div className="receipt-preview receipt-preview--error">{error}</div>;
  if (!url) return <div className="receipt-preview">Originalbeleg wird geladen …</div>;
  if (mime === "application/pdf") {
    return <iframe className="receipt-preview-frame" src={url} title="Originalbeleg" />;
  }
  if (mime === "application/xml" || mime === "text/xml") {
    return (
      <div className="receipt-preview receipt-preview--e-rechnung">
        <h3>E-Rechnung (XML)</h3>
        <p className="auth-hint">Die Werte rechts stammen direkt aus den Rechnungsdaten, nicht aus einer Texterkennung.</p>
        <dl className="e-rechnung-daten">
          {receipt.rechnungsnummer && (<><dt>Rechnungsnummer</dt><dd>{receipt.rechnungsnummer}</dd></>)}
          {receipt.anbieter.wert && (<><dt>Rechnungssteller</dt><dd>{receipt.anbieter.wert}</dd></>)}
          {receipt.datum.wert && (<><dt>Rechnungsdatum</dt><dd>{formatDate(receipt.datum.wert)}</dd></>)}
          {receipt.faelligkeit && (<><dt>Fällig am</dt><dd>{formatDate(receipt.faelligkeit)}</dd></>)}
          {receipt.betrag.wert && (<><dt>Gesamtbetrag</dt><dd>{formatMoney(receipt.betrag.wert)}</dd></>)}
          {receipt.iban && (<><dt>IBAN</dt><dd>{receipt.iban}</dd></>)}
        </dl>
        <a className="auth-link" href={url} download={`e-rechnung-${receipt.rechnungsnummer ?? receiptId}.xml`}>
          Original-XML herunterladen
        </a>
      </div>
    );
  }
  return <img className="receipt-preview-image" src={url} alt="Originalbeleg" />;
}

function ConfirmForm({ accessToken, receipt, onBooked }: { accessToken: string; receipt: Receipt; onBooked: () => void }) {
  const [betrag, setBetrag] = useState(receipt.betrag.wert ?? "");
  const [datum, setDatum] = useState(receipt.datum.wert ?? "");
  const [zahlungsdatum, setZahlungsdatum] = useState(receipt.zahlungsdatum_vorschlag ?? receipt.datum.wert ?? "");
  const [anbieter, setAnbieter] = useState(receipt.anbieter.wert ?? "");
  const [ustSatz, setUstSatz] = useState(receipt.ust_satz.wert ?? "");
  const vorschlag = receipt.steueranteile_vorschlag;
  const [gemischteUst, setGemischteUst] = useState(Boolean(vorschlag?.length));
  const [steueranteile, setSteueranteile] = useState<Steueranteil[]>(
    vorschlag?.length
      ? vorschlag.map((anteil) => ({ ust_satz: String(Number(anteil.ust_satz)), bruttobetrag: anteil.bruttobetrag }))
      : [
          { ust_satz: "7", bruttobetrag: "" },
          { ust_satz: "19", bruttobetrag: "" },
        ],
  );
  const [kategorie, setKategorie] = useState(receipt.kategorie_vorschlag.wert ?? "");
  const [konto, setKonto] = useState(receipt.buchungskonto_vorschlag ?? "");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const [lernHinweis, setLernHinweis] = useState("");

  // Wer den Anbieter anpasst, bekommt Kategorie, Konto und USt aus frueheren Buchungen
  // nachgeladen, aber nur in leere Felder. Ohne Treffer bleibt alles wie es ist.
  async function ladeGelerntes() {
    if (kategorie.trim() !== "" || anbieter.trim() === "") return;
    try {
      const vorschlag = await ladeLernvorschlag(accessToken, anbieter.trim());
      if (!vorschlag.gefunden || !vorschlag.kategorie) return;
      setKategorie(vorschlag.kategorie);
      if (vorschlag.konto) setKonto(vorschlag.konto);
      if (vorschlag.ust_satz && ustSatz.trim() === "") setUstSatz(vorschlag.ust_satz);
      setLernHinweis(vorschlag.begruendung ?? "");
    } catch {
      // Vorschlaege sind optional: Fehler (z. B. Netzwerkfehler) blockieren das Formular nicht.
    }
  }

  function updateSteueranteil(index: number, field: keyof Steueranteil, value: string) {
    setSteueranteile((current) => current.map((entry, i) => i === index ? { ...entry, [field]: value } : entry));
  }

  function addSteueranteil() {
    setSteueranteile((current) => [...current, { ust_satz: "0", bruttobetrag: "" }]);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const aktiveAnteile = steueranteile.filter((entry) => entry.bruttobetrag.trim() !== "");
      await bestaetigeBeleg(accessToken, receipt.id, {
        betrag,
        datum,
        zahlungsdatum,
        anbieter,
        ...(gemischteUst ? { steueranteile: aktiveAnteile } : { ust_satz: ustSatz }),
        kategorie,
        konto,
      });
      onBooked();
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Bestaetigen ist fehlgeschlagen.");
    }
  }

  return (
    <div className="receipt-review-container">
    <div className="receipt-review-layout">
      <ReceiptPreview accessToken={accessToken} receipt={receipt} />
      <form className="confirm-row" onSubmit={handleSubmit}>
        {receipt.begruendung && (
          <p className="hinweis"><span className="tag-unklar">Buchungsvorschlag</span> {receipt.begruendung}</p>
        )}
        {receipt.hinweise.map((hinweis) => (
          <p className="hinweis" key={hinweis}><span className="tag-unklar">Hinweis</span> {hinweis}</p>
        ))}
        {receipt.zahlungsdatum_vorschlag && (
          <p className="hinweis"><span className="tag-unklar">Kontoauszug</span> Das Zahlungsdatum stammt aus der zugeordneten Zahlung.</p>
        )}
        {lernHinweis && <p className="hinweis"><span className="tag-unklar">Gelernt</span> {lernHinweis}</p>}
        <div className="field-row">
          <div><label>Betrag</label><input value={betrag} onChange={(e) => setBetrag(e.target.value)} placeholder="z.B. 42.50" required /></div>
          <div><label>Belegdatum</label><input type="date" value={datum} onChange={(e) => setDatum(e.target.value)} required /></div>
          <div><label>Zahlungsdatum</label><input type="date" value={zahlungsdatum} onChange={(e) => setZahlungsdatum(e.target.value)} required /></div>
        </div>
        <div className="field-row">
          <div><label>Anbieter</label><input value={anbieter} onChange={(e) => setAnbieter(e.target.value)} onBlur={ladeGelerntes} required /></div>
          {!gemischteUst && (
            <div><label>USt %</label><input value={ustSatz} onChange={(e) => setUstSatz(e.target.value)} placeholder="19.00" required /></div>
          )}
          <div><label>Kategorie</label><input value={kategorie} onChange={(e) => setKategorie(e.target.value)} required /></div>
          <div><label>Buchungskonto (SKR03)</label><input value={konto} onChange={(e) => setKonto(e.target.value)} required /></div>
        </div>

        <label className="receipt-tax-toggle">
          <input type="checkbox" checked={gemischteUst} onChange={(e) => setGemischteUst(e.target.checked)} />
          Mehrere USt-Sätze auf diesem Beleg
        </label>

        {gemischteUst && (
          <div className="receipt-tax-splits">
            {steueranteile.map((entry, index) => (
              <div className="receipt-tax-split" key={index}>
                <label>
                  USt %
                  <select value={entry.ust_satz} onChange={(e) => updateSteueranteil(index, "ust_satz", e.target.value)}>
                    <option value="0">0 %</option>
                    <option value="7">7 %</option>
                    <option value="19">19 %</option>
                  </select>
                </label>
                <label>
                  Bruttobetrag
                  <input
                    inputMode="decimal"
                    value={entry.bruttobetrag}
                    onChange={(e) => updateSteueranteil(index, "bruttobetrag", e.target.value)}
                    placeholder="0.00"
                  />
                </label>
              </div>
            ))}
            <button type="button" className="auth-link" onClick={addSteueranteil}>Weiteren USt-Anteil hinzufügen</button>
            <p className="auth-hint">Die Bruttobeträge der Aufteilung müssen zusammen dem Gesamtbetrag entsprechen.</p>
          </div>
        )}

        {status === "error" && <p className="auth-error" role="alert">{error}</p>}
        <button type="submit" disabled={status === "loading"}>{status === "loading" ? "Wird gebucht …" : "Bestätigen und buchen"}</button>
      </form>
    </div>
    </div>
  );
}

export function ReceiptList({ accessToken, belege, onChanged }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState("");

  async function handleDelete(belegId: string) {
    setDeletingId(belegId);
    setDeleteError("");
    try {
      await deleteBeleg(accessToken, belegId);
      if (openId === belegId) setOpenId(null);
      onChanged();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Beleg konnte nicht geloescht werden.");
    } finally {
      setDeletingId(null);
    }
  }

  if (belege.length === 0) {
    return (
      <div className="empty-state">
        <h2>Noch keine Belege hochgeladen</h2>
        <ul>
          <li><CheckIcon width={18} height={18} /> Lokale Texterkennung liest Betrag, Datum, Anbieter und USt automatisch aus</li>
          <li><CheckIcon width={18} height={18} /> Unklare Werte werden markiert statt geraten</li>
        </ul>
        <p className="auth-hint" style={{ margin: 0 }}>Lade oben den ersten Beleg hoch.</p>
      </div>
    );
  }

  return (
    <div className="table-scroll">
    {deleteError && <p className="auth-error" role="alert">{deleteError}</p>}
    <table className="positions-table">
      <thead>
        <tr><th>Status</th><th className="number">Betrag</th><th>Datum</th><th>Anbieter</th><th>Kategorie</th><th /></tr>
      </thead>
      <tbody>
        {belege.map((beleg) => (
          <Fragment key={beleg.id}>
            <tr data-fokus-id={beleg.id}>
              <td>
                <StatusPill status={beleg.status} />
                {beleg.beleg_typ !== "ocr" && <span className="status-pill status-pill--neutral e-rechnung-badge">E-Rechnung</span>}
              </td>
              <td className="number"><FieldCell field={beleg.betrag} art="geld" /></td>
              <td><FieldCell field={beleg.datum} art="datum" /></td>
              <td><FieldCell field={beleg.anbieter} /></td>
              <td><FieldCell field={beleg.kategorie_vorschlag} /></td>
              <td className="invoice-actions">
                {beleg.status !== "gebucht" && (
                  <>
                    <button type="button" className="auth-link" onClick={() => setOpenId(openId === beleg.id ? null : beleg.id)}>
                      {openId === beleg.id ? "Schließen" : "Prüfen & buchen"}
                    </button>
                    <button
                      type="button"
                      className="auth-link danger"
                      onClick={() => handleDelete(beleg.id)}
                      disabled={deletingId === beleg.id}
                    >
                      {deletingId === beleg.id ? "Wird gelöscht …" : "Löschen"}
                    </button>
                  </>
                )}
              </td>
            </tr>
            {openId === beleg.id && (
              <tr>
                <td colSpan={6}>
                  <ConfirmForm
                    accessToken={accessToken}
                    receipt={beleg}
                    onBooked={() => { setOpenId(null); onChanged(); }}
                  />
                </td>
              </tr>
            )}
          </Fragment>
        ))}
      </tbody>
    </table>
    </div>
  );
}
