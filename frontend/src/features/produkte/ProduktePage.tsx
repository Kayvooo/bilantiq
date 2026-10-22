import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { KeineListenTreffer, ListenWerkzeug } from "../../components/ListenWerkzeug";
import { betragSuchtext } from "../../lib/suchtext";
import { useListenFilter } from "../../lib/useListenFilter";
import { useFokus } from "../../lib/useFokus";
import { formatMoney } from "../../lib/format";
import { useIstInhaber } from "../../lib/useIstInhaber";
import { ApiError } from "../auth/api";
import { ImportAssistent } from "../stammdaten/ImportAssistent";
import { StammdatenAktionen } from "../stammdaten/StammdatenAktionen";
import {
  createLagerbewegung,
  createProdukt,
  listProdukte,
  updateProdukt,
  type LagerbewegungPayload,
  type Produkt,
  type ProduktPayload,
} from "./api";

interface Props {
  accessToken: string;
  onBack: () => void;
  /** Produkt, zu dem die Suche gesprungen ist (wird geoeffnet und markiert) */
  fokusId?: string;
  /** Aus dem Umzugsassistenten: Importassistent gleich oeffnen */
  startAktion?: "import";
}

const EMPTY_FORM = {
  bezeichnung: "",
  beschreibung: "",
  einzelpreis: "0.00",
  ust_satz: "19.00",
  einheit: "Stück",
  aktiv: true,
  lagerbestand_aktiv: false,
  artikelnummer: "",
};
type FormState = typeof EMPTY_FORM;

function heute(): string {
  return new Date().toISOString().slice(0, 10);
}

function bewegungEmptyForm(): LagerbewegungPayload {
  return { datum: heute(), typ: "zugang", menge: "0", grund: "" };
}

function toForm(produkt: Produkt): FormState {
  return {
    bezeichnung: produkt.bezeichnung,
    beschreibung: produkt.beschreibung ?? "",
    einzelpreis: produkt.einzelpreis,
    ust_satz: produkt.ust_satz,
    einheit: produkt.einheit,
    aktiv: produkt.aktiv,
    lagerbestand_aktiv: produkt.lagerbestand_aktiv,
    artikelnummer: produkt.artikelnummer ?? "",
  };
}

function toPayload(form: FormState): ProduktPayload {
  return { ...form, beschreibung: form.beschreibung || null, artikelnummer: form.artikelnummer.trim() || null };
}

function ProduktFields({ form, onChange, idPrefix }: {
  form: FormState;
  onChange: (form: FormState) => void;
  idPrefix: string;
}) {
  return (
    <>
      <div className="field-row">
        <div>
          <label htmlFor={`${idPrefix}-bezeichnung`}>Bezeichnung</label>
          <input
            id={`${idPrefix}-bezeichnung`}
            value={form.bezeichnung}
            onChange={(event) => onChange({ ...form, bezeichnung: event.target.value })}
            placeholder="z. B. Strategieberatung"
            required
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-artikelnummer`}>Artikelnummer</label>
          <input
            id={`${idPrefix}-artikelnummer`}
            value={form.artikelnummer}
            onChange={(event) => onChange({ ...form, artikelnummer: event.target.value })}
            placeholder="optional"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-einheit`}>Einheit</label>
          <input
            id={`${idPrefix}-einheit`}
            value={form.einheit}
            onChange={(event) => onChange({ ...form, einheit: event.target.value })}
            placeholder="Stück oder Stunde"
            required
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-preis`}>Einzelpreis (netto)</label>
          <input
            id={`${idPrefix}-preis`}
            type="number"
            min="0"
            step="0.01"
            value={form.einzelpreis}
            onChange={(event) => onChange({ ...form, einzelpreis: event.target.value })}
            required
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-ust`}>USt %</label>
          <input
            id={`${idPrefix}-ust`}
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={form.ust_satz}
            onChange={(event) => onChange({ ...form, ust_satz: event.target.value })}
            required
          />
        </div>
      </div>
      <label htmlFor={`${idPrefix}-beschreibung`}>Beschreibung (optional)</label>
      <textarea
        id={`${idPrefix}-beschreibung`}
        value={form.beschreibung}
        onChange={(event) => onChange({ ...form, beschreibung: event.target.value })}
        maxLength={500}
        rows={3}
      />
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={form.aktiv}
          onChange={(event) => onChange({ ...form, aktiv: event.target.checked })}
        />
        Aktiv und für neue Vorgänge verfügbar
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={form.lagerbestand_aktiv}
          onChange={(event) => onChange({ ...form, lagerbestand_aktiv: event.target.checked })}
        />
        Lagerbestand für dieses Produkt verfolgen
      </label>
    </>
  );
}

function BestandForm({ form, onChange, idPrefix }: {
  form: LagerbewegungPayload;
  onChange: (form: LagerbewegungPayload) => void;
  idPrefix: string;
}) {
  return (
    <div className="field-row">
      <div>
        <label htmlFor={`${idPrefix}-datum`}>Datum</label>
        <input
          id={`${idPrefix}-datum`}
          type="date"
          value={form.datum}
          onChange={(event) => onChange({ ...form, datum: event.target.value })}
          required
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-typ`}>Art</label>
        <select
          id={`${idPrefix}-typ`}
          value={form.typ}
          onChange={(event) => onChange({ ...form, typ: event.target.value as LagerbewegungPayload["typ"] })}
        >
          <option value="zugang">Wareneingang (Zugang)</option>
          <option value="abgang">Warenausgang (Abgang)</option>
        </select>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-menge`}>Menge</label>
        <input
          id={`${idPrefix}-menge`}
          type="number"
          min="0"
          step="0.001"
          value={form.menge}
          onChange={(event) => onChange({ ...form, menge: event.target.value })}
          required
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-grund`}>Grund</label>
        <input
          id={`${idPrefix}-grund`}
          value={form.grund}
          onChange={(event) => onChange({ ...form, grund: event.target.value })}
          placeholder="z. B. Lieferung, Inventurkorrektur"
          required
        />
      </div>
    </div>
  );
}

export function ProduktePage({ accessToken, onBack, fokusId, startAktion }: Props) {
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [produkte, setProdukte] = useState<Produkt[]>([]);
  const [createForm, setCreateForm] = useState<FormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [bestandId, setBestandId] = useState<string | null>(null);
  const [bestandForm, setBestandForm] = useState<LagerbewegungPayload>(bewegungEmptyForm());
  const [booking, setBooking] = useState(false);
  const [importOffen, setImportOffen] = useState(startAktion === "import");
  const istInhaber = useIstInhaber(accessToken);
  const werkzeug = useListenFilter(produkte, {
    suchtext: (p) => [p.bezeichnung, p.artikelnummer, p.beschreibung, betragSuchtext(p.einzelpreis)].filter(Boolean).join(" "),
    filter: [
      { id: "aktiv", label: "Aktiv", passt: (p) => p.aktiv },
      { id: "inaktiv", label: "Inaktiv", passt: (p) => !p.aktiv },
      { id: "lager", label: "Mit Lagerbestand", passt: (p) => p.lagerbestand_aktiv },
    ],
    sortierungen: [
      { id: "preis-auf", label: "Preis, niedrigster zuerst", vergleiche: (a, b) => Number(a.einzelpreis) - Number(b.einzelpreis) },
      { id: "preis-ab", label: "Preis, höchster zuerst", vergleiche: (a, b) => Number(b.einzelpreis) - Number(a.einzelpreis) },
      { id: "artikelnummer", label: "Artikelnummer", vergleiche: (a, b) => (a.artikelnummer ?? "").localeCompare(b.artikelnummer ?? "", "de", { numeric: true }) },
    ],
  });

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setProdukte(await listProdukte(accessToken));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Produkte konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  // Sprung aus der Suche: Produkt oeffnen und markieren.
  const fokusErledigt = useRef<string | null>(null);
  useEffect(() => {
    if (!fokusId || loadStatus !== "ready" || fokusErledigt.current === fokusId) return;
    fokusErledigt.current = fokusId;
    const treffer = produkte.find((p) => p.id === fokusId);
    if (treffer) startEdit(treffer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fokusId, loadStatus, produkte]);
  useFokus(fokusId, loadStatus === "ready" && produkte.some((p) => p.id === fokusId));

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      await createProdukt(accessToken, toPayload(createForm));
      setCreateForm(EMPTY_FORM);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Produkt konnte nicht angelegt werden.");
    } finally {
      setCreating(false);
    }
  }

  function startEdit(produkt: Produkt) {
    setBestandId(null);
    setEditId(produkt.id);
    setEditForm(toForm(produkt));
  }

  async function handleSaveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editId) return;
    setSaving(true);
    setError("");
    try {
      await updateProdukt(accessToken, editId, toPayload(editForm));
      setEditId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Produkt konnte nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  }

  function startBooking(produkt: Produkt) {
    setEditId(null);
    setBestandId(produkt.id);
    setBestandForm(bewegungEmptyForm());
  }

  async function handleBooking(event: FormEvent) {
    event.preventDefault();
    if (!bestandId) return;
    setBooking(true);
    setError("");
    try {
      await createLagerbewegung(accessToken, bestandId, bestandForm);
      setBestandId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bestand konnte nicht gebucht werden.");
    } finally {
      setBooking(false);
    }
  }

  if (loadStatus === "loading") return <PageState label="Produkte werden geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;

  return (
    <div className="invoices-page">
      <PageHeader
        title="Produkte" description="Produkte und Leistungen als wiederverwendbare Stammdaten." onBack={onBack}
        action={
          <StammdatenAktionen
            accessToken={accessToken} ziel="produkte" istInhaber={istInhaber} onFehler={setError}
            onImportieren={() => setImportOffen(true)}
          />
        }
      />
      {error && <p className="auth-error" role="alert">{error}</p>}

      {importOffen ? (
        <ImportAssistent
          accessToken={accessToken} ziel="produkte"
          onAbbrechen={() => setImportOffen(false)}
          onFertig={() => { setImportOffen(false); void load(); }}
        />
      ) : (
        <form className="panel" onSubmit={handleCreate}>
          <h2>Neues Produkt</h2>
          <ProduktFields form={createForm} onChange={setCreateForm} idPrefix="new-product" />
          <button type="submit" disabled={creating}>{creating ? "Wird angelegt …" : "Produkt anlegen"}</button>
        </form>
      )}

      <h2 className="section-title">Alle Produkte</h2>
      {produkte.length === 0 ? (
        <div className="empty-state">
          <h2>Noch keine Produkte</h2>
          <p className="auth-hint" style={{ margin: 0 }}>
            Lege oben das erste Produkt oder eine Leistung an{istInhaber ? " oder übernimm deine Artikelliste aus einer Excel- oder CSV-Datei" : ""}.
          </p>
          {istInhaber && !importOffen && (
            <div className="actions">
              <button type="button" className="auth-link" onClick={() => setImportOffen(true)}>Aus Excel oder altem Programm übernehmen</button>
            </div>
          )}
        </div>
      ) : (
        <>
          <ListenWerkzeug steuerung={werkzeug} placeholder="Bezeichnung oder Artikelnummer" ariaLabel="Produkte durchsuchen" />
          {werkzeug.sichtbar.length === 0 ? <KeineListenTreffer onZuruecksetzen={werkzeug.zuruecksetzen} /> : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead><tr><th>Bezeichnung</th><th>Einheit</th><th className="number">Netto</th><th className="number">USt</th><th className="number">Bestand</th><th>Status</th><th /></tr></thead>
            <tbody>
              {werkzeug.sichtbar.map((produkt) => (
                <Fragment key={produkt.id}>
                  <tr data-fokus-id={produkt.id}>
                    <td>
                      {produkt.bezeichnung}
                      {produkt.artikelnummer && <div className="zelle-nebentext">Art.-Nr. {produkt.artikelnummer}</div>}
                    </td>
                    <td>{produkt.einheit}</td>
                    <td className="number">{formatMoney(produkt.einzelpreis)}</td>
                    <td className="number">{Number(produkt.ust_satz).toLocaleString("de-DE")} %</td>
                    <td className="number">
                      {produkt.lagerbestand_aktiv && produkt.lagerbestand !== null
                        ? `${Number(produkt.lagerbestand).toLocaleString("de-DE")} ${produkt.einheit}`
                        : "—"}
                    </td>
                    <td>{produkt.aktiv ? "Aktiv" : "Inaktiv"}</td>
                    <td className="invoice-actions">
                      <button type="button" className="auth-link" onClick={() => editId === produkt.id ? setEditId(null) : startEdit(produkt)}>{editId === produkt.id ? "Schließen" : "Bearbeiten"}</button>
                      {produkt.lagerbestand_aktiv && (
                        <button type="button" className="auth-link" onClick={() => bestandId === produkt.id ? setBestandId(null) : startBooking(produkt)}>
                          {bestandId === produkt.id ? "Schließen" : "Bestand buchen"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {editId === produkt.id && (
                    <tr><td colSpan={7}>
                      <form className="confirm-row" onSubmit={handleSaveEdit}>
                        <ProduktFields form={editForm} onChange={setEditForm} idPrefix={`edit-product-${produkt.id}`} />
                        <button type="submit" disabled={saving}>{saving ? "Wird gespeichert …" : "Speichern"}</button>
                      </form>
                    </td></tr>
                  )}
                  {bestandId === produkt.id && (
                    <tr><td colSpan={7}>
                      <form className="confirm-row" onSubmit={handleBooking}>
                        <BestandForm form={bestandForm} onChange={setBestandForm} idPrefix={`bestand-${produkt.id}`} />
                        <button type="submit" disabled={booking}>{booking ? "Wird gebucht …" : "Buchen"}</button>
                      </form>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
          )}
        </>
      )}
    </div>
  );
}
