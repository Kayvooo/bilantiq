import { useEffect, useRef, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { dezimalEingabe } from "../../lib/decimalInput";
import { formatMoney } from "../../lib/format";
import { PdfPreviewFrame, type ZoomStufe } from "../../components/PdfPreviewFrame";
import { ApiError, listMitglieder, type Mitglied } from "../auth/api";
import { RechnungsdesignPanel } from "../auth/RechnungsdesignPanel";
import {
  ustSatzFuerNeuePosition,
  type Buchhaltungseinstellungen,
} from "../buchhaltungseinstellungen/api";
import {
  createInvoice,
  finalizeInvoice,
  listPositionskategorien,
  previewInvoice,
  type Invoice,
  type InvoiceDraft,
  type InvoicePosition,
  type Kontakt,
  type Positionskategorie,
} from "./api";

interface Props {
  accessToken: string;
  kontakte: Kontakt[];
  einstellungen: Buchhaltungseinstellungen;
  onCreated: (invoice: Invoice) => void;
  onBack: () => void;
  onNewKontakt: () => void;
  initialTab?: "inhalt" | "design";
  initialDraft?: InvoiceDraft;
}

const ZAHLUNGSMETHODEN = [
  { wert: "sepa_ueberweisung", label: "SEPA-Überweisung" },
  { wert: "ueberweisung", label: "Überweisung" },
  { wert: "lastschrift", label: "Lastschrift" },
  { wert: "bar", label: "Bar" },
  { wert: "sonstiges", label: "Sonstiges" },
];

const LEER_POSITION: InvoicePosition = { beschreibung: "", menge: "1", einzelpreis: "0.00", ust_satz: "19.00", kategorie: "", artikelnummer: "" };

function heute(offsetTage = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetTage);
  return d.toISOString().slice(0, 10);
}

function bruttoAus(einzelpreis: string, ustSatz: string): string {
  const netto = Number(einzelpreis) || 0;
  const ust = Number(ustSatz) || 0;
  return (netto * (1 + ust / 100)).toFixed(2);
}

function nettoAusBrutto(brutto: string, ustSatz: string): string {
  const b = Number(brutto) || 0;
  const ust = Number(ustSatz) || 0;
  return (b / (1 + ust / 100)).toFixed(2);
}

export function InvoiceEditor({ accessToken, kontakte, einstellungen, onCreated, onBack, onNewKontakt, initialTab, initialDraft }: Props) {
  const standardUstSatz = ustSatzFuerNeuePosition(einstellungen);
  const [tab, setTab] = useState<"inhalt" | "design">(initialTab ?? "inhalt");
  const [zoom, setZoom] = useState<ZoomStufe>(75);
  const rechnungsKontakte = kontakte.filter((k) => k.typ !== "lieferant" || k.id === initialDraft?.kontakt_id);
  const startKontakt = initialDraft ? undefined : rechnungsKontakte[0];
  const zahlungszielTage = (kontakt?: Kontakt) => kontakt?.zahlungsziel_tage ?? einstellungen.standard_zahlungsziel_tage;
  const [kontaktId, setKontaktId] = useState(initialDraft?.kontakt_id ?? startKontakt?.id ?? "");
  const [leistungsdatum, setLeistungsdatum] = useState(initialDraft?.leistungsdatum ?? heute());
  const [faelligkeitsdatum, setFaelligkeitsdatum] = useState(initialDraft?.faelligkeitsdatum ?? heute(zahlungszielTage(startKontakt)));
  const [betreff, setBetreff] = useState(initialDraft?.betreff ?? "Rechnung");
  const [kopftext, setKopftext] = useState(
    initialDraft?.kopftext ?? "Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihren Auftrag und das damit verbundene Vertrauen!\nHiermit stelle ich Ihnen die folgenden Leistungen in Rechnung:",
  );
  const [fusstext, setFusstext] = useState(
    initialDraft?.fusstext ?? "Bitte überweisen Sie den Rechnungsbetrag unter Angabe der Rechnungsnummer auf das unten angegebene Konto.\nDer Rechnungsbetrag ist bis zum [%ZAHLUNGSZIEL%] fällig.",
  );
  const [referenznummer, setReferenznummer] = useState(initialDraft?.referenznummer ?? "");
  const [kostenstelle, setKostenstelle] = useState(initialDraft?.kostenstelle ?? "");
  const [zahlungsmethode, setZahlungsmethode] = useState(initialDraft?.zahlungsmethode ?? "sepa_ueberweisung");
  const [skontoTage, setSkontoTage] = useState(
    initialDraft ? (initialDraft.skonto_tage != null ? String(initialDraft.skonto_tage) : "") : startKontakt?.skonto_tage != null ? String(startKontakt.skonto_tage) : "",
  );
  const [skontoProzent, setSkontoProzent] = useState(initialDraft ? initialDraft.skonto_prozent ?? "" : startKontakt?.skonto_prozent ?? "");
  const [interneKontaktpersonId, setInterneKontaktpersonId] = useState(initialDraft?.interne_kontaktperson_user_id ?? "");
  const [positionen, setPositionen] = useState<InvoicePosition[]>(
    initialDraft?.positionen?.length
      ? initialDraft.positionen.map((p) => ({ ...p }))
      : [{ ...LEER_POSITION, ust_satz: standardUstSatz }],
  );
  const [bruttoModus, setBruttoModus] = useState(false);

  const [mitglieder, setMitglieder] = useState<Mitglied[]>([]);
  const [kategorien, setKategorien] = useState<Positionskategorie[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "error">("idle");
  const previewUrlRef = useRef<string | null>(null);
  const vorschauAnfrageRef = useRef(0);

  useEffect(() => {
    listMitglieder(accessToken).then(setMitglieder).catch(() => {});
    listPositionskategorien(accessToken).then(setKategorien).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  useEffect(
    () => () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    },
    [],
  );

  // Live-Vorschau: kurz nach der letzten Eingabe neu rendern, nicht erst beim Verlassen
  // eines Feldes. Leere Pflichtfelder werden nur fuer die Vorschau mit Platzhaltern
  // gefuellt, damit sie sofort etwas zeigt.
  const vorschauSchluessel = JSON.stringify(baueVorschauDraft());
  useEffect(() => {
    if (!kontaktId) {
      setPreviewStatus("idle");
      return;
    }
    const timer = window.setTimeout(() => {
      void aktualisiereVorschau();
    }, 400);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vorschauSchluessel, kontaktId]);

  function baueDraft() {
    return {
      kontakt_id: kontaktId,
      leistungsdatum,
      faelligkeitsdatum,
      waehrung: "EUR",
      positionen: positionen.map((p) => ({ ...p, kategorie: p.kategorie || undefined, artikelnummer: p.artikelnummer || undefined })),
      betreff: betreff || undefined,
      kopftext: kopftext || undefined,
      fusstext: fusstext || undefined,
      referenznummer: referenznummer || undefined,
      kostenstelle: kostenstelle || undefined,
      zahlungsmethode: zahlungsmethode || undefined,
      skonto_tage: skontoTage ? Number(skontoTage) : undefined,
      skonto_prozent: skontoProzent || undefined,
      interne_kontaktperson_user_id: interneKontaktpersonId || undefined,
    };
  }

  function baueVorschauDraft() {
    const draft = baueDraft();
    const zahl = (wert: string, ersatz: string) => (wert.trim() !== "" && Number.isFinite(Number(wert)) ? wert : ersatz);
    return {
      ...draft,
      leistungsdatum: draft.leistungsdatum || heute(),
      faelligkeitsdatum: draft.faelligkeitsdatum || heute(einstellungen.standard_zahlungsziel_tage),
      positionen: draft.positionen.map((p) => ({
        ...p,
        beschreibung: p.beschreibung.trim() || "Beschreibung der Leistung",
        menge: Number(p.menge) > 0 ? p.menge : "1",
        einzelpreis: zahl(p.einzelpreis, "0.00"),
        ust_satz: zahl(p.ust_satz, "19.00"),
      })),
    };
  }

  async function aktualisiereVorschau() {
    const anfrage = ++vorschauAnfrageRef.current;
    setPreviewStatus("loading");
    try {
      const blob = await previewInvoice(accessToken, baueVorschauDraft());
      if (anfrage !== vorschauAnfrageRef.current) return;
      const url = URL.createObjectURL(blob);
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = url;
      setPreviewUrl(url);
      setPreviewStatus("idle");
    } catch {
      if (anfrage === vorschauAnfrageRef.current) setPreviewStatus("error");
    }
  }

  const gewaehlterKontakt = kontakte.find((k) => k.id === kontaktId);
  const zeigtHinweis = gewaehlterKontakt?.land === "DE" && gewaehlterKontakt?.ist_geschaeftskunde;

  /** Zahlungsziel und Skonto kommen aus dem Kontakt, sonst aus den Buchhaltungseinstellungen.
   * Skonto des vorherigen Kontakts wird nur entfernt, wenn es unveraendert uebernommen war. */
  function waehleKontakt(id: string) {
    const vorher = gewaehlterKontakt;
    const neu = kontakte.find((k) => k.id === id);
    setKontaktId(id);
    if (!neu) return;
    setFaelligkeitsdatum(heute(zahlungszielTage(neu)));
    if (neu.skonto_prozent) {
      setSkontoProzent(neu.skonto_prozent);
      setSkontoTage(neu.skonto_tage != null ? String(neu.skonto_tage) : "");
    } else if (vorher?.skonto_prozent && vorher.skonto_prozent === skontoProzent) {
      setSkontoProzent("");
      setSkontoTage("");
    }
  }

  function updatePosition(index: number, field: keyof InvoicePosition, value: string) {
    const eingabe = field === "menge" || field === "ust_satz" ? dezimalEingabe(value) : value;
    setPositionen((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: eingabe } : p)));
  }

  function updatePositionPreis(index: number, roh: string) {
    const eingabe = dezimalEingabe(roh);
    setPositionen((prev) =>
      prev.map((p, i) => {
        if (i !== index) return p;
        return bruttoModus ? { ...p, einzelpreis: nettoAusBrutto(eingabe, p.ust_satz) } : { ...p, einzelpreis: eingabe };
      }),
    );
  }

  function anzeigePreis(p: InvoicePosition): string {
    return bruttoModus ? bruttoAus(p.einzelpreis, p.ust_satz) : p.einzelpreis;
  }

  function addPosition() {
    setPositionen((prev) => [...prev, { ...LEER_POSITION, ust_satz: standardUstSatz }]);
  }

  function removePosition(index: number) {
    setPositionen((prev) => prev.filter((_, i) => i !== index));
  }

  const netto = positionen.reduce((sum, p) => sum + (Number(p.menge) || 0) * (Number(p.einzelpreis) || 0), 0);
  const ust = positionen.reduce((sum, p) => sum + (Number(p.menge) || 0) * (Number(p.einzelpreis) || 0) * ((Number(p.ust_satz) || 0) / 100), 0);

  async function speichern(abschliessen: boolean) {
    if (!kontaktId) {
      setStatus("error");
      setError("Bitte zuerst einen Kontakt anlegen oder auswählen.");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      let invoice = await createInvoice(accessToken, baueDraft());
      if (abschliessen) invoice = await finalizeInvoice(accessToken, invoice.id);
      onCreated(invoice);
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Rechnung konnte nicht erstellt werden.");
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await speichern(false);
  }

  return (
    <div className="invoices-page">
      <PageHeader
        title={tab === "design" ? "Rechnungsdesign" : "Rechnung erstellen"}
        description={tab === "design" ? "Gilt für alle künftigen Rechnungen, Angebote, Auftragsbestätigungen und Lieferscheine." : "Inhalt links, Ergebnis live rechts."}
        onBack={onBack}
      />

      {error && <p className="auth-error" role="alert">{error}</p>}

      <div className="pill-row editor-tabs" role="tablist" aria-label="Rechnungs-Editor">
        <button type="button" role="tab" aria-selected={tab === "inhalt"} className={`pill${tab === "inhalt" ? " pill--aktiv" : ""}`} onClick={() => setTab("inhalt")}>
          Inhalt
        </button>
        <button type="button" role="tab" aria-selected={tab === "design"} className={`pill${tab === "design" ? " pill--aktiv" : ""}`} onClick={() => setTab("design")}>
          Design
        </button>
      </div>

      {tab === "design" ? (
        <RechnungsdesignPanel accessToken={accessToken} />
      ) : rechnungsKontakte.length === 0 ? (
        <div className="panel">
          <h2>Neue Rechnung</h2>
          <p className="auth-hint">Noch kein Kontakt vorhanden. Lege zuerst einen an.</p>
          <button type="button" onClick={onNewKontakt}>Kontakt anlegen</button>
        </div>
      ) : (
      <div className="vorlage-layout">
        <form className="panel" onSubmit={handleSubmit}>
          <h2>Empfänger</h2>
          <label htmlFor="ed-kontakt">Kontakt</label>
          <select id="ed-kontakt" value={kontaktId} onChange={(e) => waehleKontakt(e.target.value)}>
            {rechnungsKontakte.map((k) => (<option key={k.id} value={k.id}>{k.name}</option>))}
          </select>
          <button type="button" className="auth-link" onClick={onNewKontakt}>+ neuer Kontakt</button>

          {gewaehlterKontakt?.leitweg_id && (
            <p className="hinweis">
              Öffentlicher Auftraggeber: Die Leitweg-ID {gewaehlterKontakt.leitweg_id} steht als Käuferreferenz in der XRechnung.
              Exportiere diese Rechnung nach dem Abschließen als XRechnung.
            </p>
          )}

          {zeigtHinweis && (
            <p className="hinweis">
              B2B-Kunde in Deutschland: Diese Rechnung sollte als E-Rechnung ausgestellt werden können
              (seit 1.1.2025 Pflicht).
            </p>
          )}

          <h2>Rechnungsinformationen</h2>
          <div className="field-row">
            <div>
              <label htmlFor="ed-leistung">Leistungsdatum</label>
              <input id="ed-leistung" type="date" value={leistungsdatum} onChange={(e) => setLeistungsdatum(e.target.value)} required />
            </div>
            <div>
              <label htmlFor="ed-faellig">Zahlungsziel</label>
              <input id="ed-faellig" type="date" value={faelligkeitsdatum} onChange={(e) => setFaelligkeitsdatum(e.target.value)} required />
            </div>
          </div>
          <label htmlFor="ed-referenz">Referenznummer</label>
          <input id="ed-referenz" value={referenznummer} onChange={(e) => setReferenznummer(e.target.value)} placeholder="z.B. Bestellnummer der Kundschaft" />

          <h2>Kopftext</h2>
          <label htmlFor="ed-betreff">Betreff</label>
          <input id="ed-betreff" value={betreff} onChange={(e) => setBetreff(e.target.value)} required />
          <label htmlFor="ed-kopftext">Einleitungstext</label>
          <textarea id="ed-kopftext" rows={4} value={kopftext} onChange={(e) => setKopftext(e.target.value)} />
          <p className="auth-hint">Wird aktuell im Editor gespeichert, erscheint aber noch nicht auf dem PDF selbst.</p>

          <h2>Positionen</h2>
          <div className="checkbox-row" style={{ marginBottom: 8 }}>
            <input id="ed-brutto" type="checkbox" checked={bruttoModus} onChange={(e) => setBruttoModus(e.target.checked)} />
            <label htmlFor="ed-brutto" style={{ margin: 0 }}>Preise brutto eingeben</label>
          </div>
          <div className="table-scroll">
            <table className="positions-table positions-table--stapel">
              <thead>
                <tr><th>Beschreibung</th><th>Art.-Nr.</th><th>Kategorie</th><th>Menge</th><th>{bruttoModus ? "Preis brutto" : "Einzelpreis"}</th><th>USt %</th><th /></tr>
              </thead>
              <tbody>
                {positionen.map((p, i) => (
                  <tr key={i}>
                    <td data-label="Beschreibung"><input aria-label={`Beschreibung, Position ${i + 1}`} value={p.beschreibung} onChange={(e) => updatePosition(i, "beschreibung", e.target.value)} required /></td>
                    <td data-label="Art.-Nr.">
                      <input
                        aria-label={`Artikelnummer, Position ${i + 1}`}
                        value={p.artikelnummer ?? ""} onChange={(e) => updatePosition(i, "artikelnummer", e.target.value)}
                        placeholder="optional"
                      />
                    </td>
                    <td data-label="Kategorie">
                      <input
                        aria-label={`Kategorie, Position ${i + 1}`}
                        value={p.kategorie ?? ""} onChange={(e) => updatePosition(i, "kategorie", e.target.value)}
                        list="ed-kategorien" placeholder="optional"
                      />
                    </td>
                    <td data-label="Menge"><input aria-label={`Menge, Position ${i + 1}`} inputMode="decimal" value={p.menge} onChange={(e) => updatePosition(i, "menge", e.target.value)} required /></td>
                    <td data-label={bruttoModus ? "Preis brutto" : "Einzelpreis"}><input aria-label={`${bruttoModus ? "Preis brutto" : "Einzelpreis"}, Position ${i + 1}`} inputMode="decimal" value={anzeigePreis(p)} onChange={(e) => updatePositionPreis(i, e.target.value)} required /></td>
                    <td data-label="USt %"><input aria-label={`Umsatzsteuersatz in Prozent, Position ${i + 1}`} inputMode="decimal" value={p.ust_satz} onChange={(e) => updatePosition(i, "ust_satz", e.target.value)} required /></td>
                    <td data-label="">
                      {positionen.length > 1 && (
                        <button type="button" className="auth-link danger" onClick={() => removePosition(i)}>entfernen</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <datalist id="ed-kategorien">
            {kategorien.map((k) => (<option key={k.id} value={k.name} />))}
          </datalist>
          <button type="button" className="auth-link" onClick={addPosition}>+ Position</button>

          <div className="editor-summe">
            <div><span>Netto</span><span className="number">{formatMoney(netto.toFixed(2))}</span></div>
            <div><span>USt</span><span className="number">{formatMoney(ust.toFixed(2))}</span></div>
            <div className="editor-summe-gesamt"><span>Gesamt</span><span className="number">{formatMoney((netto + ust).toFixed(2))}</span></div>
          </div>

          <h2 id="ed-fusstext-titel">Fußtext</h2>
          <textarea id="ed-fusstext" aria-labelledby="ed-fusstext-titel" rows={4} value={fusstext} onChange={(e) => setFusstext(e.target.value)} />
          <p className="auth-hint">Platzhalter <code>[%ZAHLUNGSZIEL%]</code> und <code>[%KONTAKTPERSON%]</code> werden beim Erzeugen automatisch ersetzt.</p>

          <h2>Weitere Optionen</h2>
          <div className="field-row">
            <div>
              <label htmlFor="ed-kontaktperson">Interne Kontaktperson</label>
              <select id="ed-kontaktperson" value={interneKontaktpersonId} onChange={(e) => setInterneKontaktpersonId(e.target.value)}>
                <option value="">Keine</option>
                {mitglieder.map((m) => (<option key={m.user_id} value={m.user_id}>{m.email}</option>))}
              </select>
            </div>
            <div>
              <label htmlFor="ed-kostenstelle">Kostenstelle</label>
              <input id="ed-kostenstelle" value={kostenstelle} onChange={(e) => setKostenstelle(e.target.value)} />
            </div>
          </div>
          <div className="field-row">
            <div>
              <label htmlFor="ed-zahlungsmethode">Zahlungsmethode</label>
              <select id="ed-zahlungsmethode" value={zahlungsmethode} onChange={(e) => setZahlungsmethode(e.target.value)}>
                {ZAHLUNGSMETHODEN.map((z) => (<option key={z.wert} value={z.wert}>{z.label}</option>))}
              </select>
            </div>
            <div>
              <label htmlFor="ed-skonto-tage">Skonto</label>
              <div className="farb-eingabe">
                <input id="ed-skonto-tage" value={skontoTage} onChange={(e) => setSkontoTage(e.target.value)} placeholder="Tage" style={{ width: 90 }} />
                <input aria-label="Skonto in Prozent" inputMode="decimal" value={skontoProzent} onChange={(e) => setSkontoProzent(dezimalEingabe(e.target.value))} placeholder="%" style={{ width: 90 }} />
              </div>
            </div>
          </div>

          <div className="actions">
            <button type="submit" disabled={status === "loading"}>
              {status === "loading" ? "Wird gespeichert …" : "Entwurf speichern"}
            </button>
            <button type="button" className="button-secondary" disabled={status === "loading"} onClick={() => speichern(true)}>
              Speichern und abschließen
            </button>
          </div>
        </form>

        <div className="vorlage-vorschau panel">
          <h2>Vorschau</h2>
          <PdfPreviewFrame
            title="Rechnungsvorschau"
            url={kontaktId ? previewUrl : null}
            leerHinweis={kontaktId ? "Die Vorschau erscheint hier." : "Lege zuerst einen Kontakt an, dann erscheint die Vorschau."}
            loading={previewStatus === "loading"}
            fehler={previewStatus === "error"}
            zoom={zoom}
            onZoomChange={setZoom}
          />
        </div>
      </div>
      )}
    </div>
  );
}
