import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { mitBestaetigung } from "./bestaetigung";
import { PageState } from "../../components/PageState";
import { PillAuswahl } from "../../components/PillAuswahl";
import { PdfPreviewFrame, type ZoomStufe } from "../../components/PdfPreviewFrame";
import { useRollenStatus } from "../../lib/useIstInhaber";
import {
  ApiError,
  deleteBriefpapier,
  deleteLogo,
  fetchLogoBlob,
  getMandant,
  listBriefpapier,
  previewRechnungsvorlage,
  updateMandant,
  uploadBriefpapier,
  uploadLogo,
  type Briefpapier,
  type DesignVariante,
  type LogoGroesse,
  type Mandant,
  type Rechnungsvorlage,
  type Sprache,
} from "./api";

interface Props {
  accessToken: string;
}

const VORLAGEN: { wert: Rechnungsvorlage; label: string; beschreibung: string }[] = [
  { wert: "klassisch", label: "Klassisch", beschreibung: "Schwarz auf Weiß, dünne Trennlinien — die vertraute Geschäftsbrief-Optik." },
  { wert: "modern", label: "Modern", beschreibung: "Farbiger Tabellenkopf, dezente Datenbox und klarer Gesamtbetrag." },
  { wert: "minimal", label: "Minimal", beschreibung: "Große Typografie, feine Linien und großzügiger Weißraum." },
  { wert: "kompakt", label: "Kompakt", beschreibung: "Dicht gesetzt, kleine Schrift — passt mehr auf eine Seite." },
  { wert: "elegant", label: "Elegant", beschreibung: "Zeitlose Serifenschrift und zurückhaltende Farbakzente." },
  { wert: "balken", label: "Kopfbalken", beschreibung: "Satter Farbkopf mit kontrastreichem Absender und eigenem Logo." },
  { wert: "seitenleiste", label: "Seitenleiste", beschreibung: "Schmaler geschwungener Farbrand mit viel Platz für deine Inhalte." },
  { wert: "rahmen", label: "Rahmen", beschreibung: "Feine Seitenkontur, ruhige Datenbox und dezente Tabellenzeilen." },
  { wert: "kachel", label: "Kachel", beschreibung: "Gesamtbetrag als hervorgehobene Farbkachel." },
  { wert: "mono", label: "Mono", beschreibung: "Präzise Schreibmaschinenschrift und ein reduziertes Schwarz-Weiß-Layout." },
  { wert: "stempel", label: "Stempel", beschreibung: "Großes, blasses Wasserzeichen im Hintergrund." },
];

const VARIANTEN: { wert: DesignVariante; label: string }[] = [
  { wert: "standard", label: "Standard" },
  { wert: "schwarz", label: "Schwarz" },
  { wert: "blau", label: "Blau" },
  { wert: "einfach", label: "Einfach" },
];

const SPRACHEN = [
  { wert: "de", label: "Deutsch" },
  { wert: "en", label: "English" },
] as const;
const LOGO_GROESSEN: { wert: LogoGroesse; label: string }[] = [
  { wert: "S", label: "Klein" },
  { wert: "M", label: "Mittel" },
  { wert: "L", label: "Groß" },
];

const ELEMENTE: { feld: keyof ToggleFelder; label: string }[] = [
  { feld: "zeige_absenderzeile", label: "Absenderzeile" },
  { feld: "zeige_kundennummer", label: "Kundennummer" },
  { feld: "zeige_kontaktperson", label: "Kontaktperson" },
  { feld: "zeige_artikelnummer", label: "Artikelnummer" },
  { feld: "zeige_positionsbeschreibung", label: "Positionsbeschreibung" },
  { feld: "zeige_ust_pro_position", label: "USt pro Position" },
  { feld: "zeige_girocode", label: "GiroCode (QR-Zahlungscode)" },
  { feld: "zeige_fusszeile", label: "Fußzeile" },
  { feld: "zeige_seitenzahlen", label: "Seitenzahlen" },
  { feld: "zeige_falz_lochmarken", label: "Falz-/Lochmarken" },
];

const STANDARD_AKZENTFARBE = "#143D2B";

interface ToggleFelder {
  zeige_absenderzeile: boolean;
  zeige_kundennummer: boolean;
  zeige_kontaktperson: boolean;
  zeige_artikelnummer: boolean;
  zeige_positionsbeschreibung: boolean;
  zeige_ust_pro_position: boolean;
  zeige_girocode: boolean;
  zeige_fusszeile: boolean;
  zeige_seitenzahlen: boolean;
  zeige_falz_lochmarken: boolean;
}

const EMPTY_FORM = {
  rechnungsvorlage: "klassisch" as Rechnungsvorlage,
  design_variante: "standard" as DesignVariante,
  akzentfarbe: STANDARD_AKZENTFARBE,
  logo_groesse: "M" as LogoGroesse,
  briefpapier_id: "",
  sprache: "de" as Sprache,
  fusszeile_text: "",
  iban: "",
  bic: "",
  zeige_absenderzeile: true,
  zeige_kundennummer: false,
  zeige_kontaktperson: false,
  zeige_artikelnummer: false,
  zeige_positionsbeschreibung: true,
  zeige_ust_pro_position: true,
  zeige_girocode: false,
  zeige_fusszeile: true,
  zeige_seitenzahlen: false,
  zeige_falz_lochmarken: false,
};
type FormState = typeof EMPTY_FORM;

function toForm(mandant: Mandant): FormState {
  return {
    rechnungsvorlage: mandant.rechnungsvorlage ?? "klassisch",
    design_variante: mandant.design_variante ?? "standard",
    akzentfarbe: mandant.akzentfarbe ?? STANDARD_AKZENTFARBE,
    logo_groesse: mandant.logo_groesse ?? "M",
    briefpapier_id: mandant.briefpapier_id ?? "",
    sprache: mandant.sprache ?? "de",
    fusszeile_text: mandant.fusszeile_text ?? "",
    iban: mandant.iban ?? "",
    bic: mandant.bic ?? "",
    zeige_absenderzeile: mandant.zeige_absenderzeile,
    zeige_kundennummer: mandant.zeige_kundennummer,
    zeige_kontaktperson: mandant.zeige_kontaktperson,
    zeige_artikelnummer: mandant.zeige_artikelnummer,
    zeige_positionsbeschreibung: mandant.zeige_positionsbeschreibung,
    zeige_ust_pro_position: mandant.zeige_ust_pro_position,
    zeige_girocode: mandant.zeige_girocode,
    zeige_fusszeile: mandant.zeige_fusszeile,
    zeige_seitenzahlen: mandant.zeige_seitenzahlen,
    zeige_falz_lochmarken: mandant.zeige_falz_lochmarken,
  };
}

export function RechnungsdesignPanel({ accessToken }: Props) {
  // IBAN/BIC stehen auf jeder Rechnung (Zahlungsumleitung): das Backend laesst nur den Inhaber sie aendern.
  // Alle Design-Felder bleiben fuer Mitglieder aenderbar.
  const bankdatenSchreibgeschuetzt = useRollenStatus(accessToken) !== "inhaber";
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [hatLogo, setHatLogo] = useState(false);
  const [logoObjectUrl, setLogoObjectUrl] = useState<string | null>(null);
  const [logoStatus, setLogoStatus] = useState<"idle" | "busy">("idle");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "error">("idle");
  const [zoom, setZoom] = useState<ZoomStufe>(75);
  const [briefpapierListe, setBriefpapierListe] = useState<Briefpapier[]>([]);
  const [briefpapierUploadOffen, setBriefpapierUploadOffen] = useState(false);
  const [briefpapierName, setBriefpapierName] = useState("");
  const [briefpapierStatus, setBriefpapierStatus] = useState<"idle" | "busy">("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const briefpapierFileRef = useRef<HTMLInputElement>(null);

  async function ladeLogoVorschau(mandant: Mandant) {
    if (!mandant.hat_logo) {
      setLogoObjectUrl(null);
      return;
    }
    try {
      const blob = await fetchLogoBlob(accessToken);
      setLogoObjectUrl(URL.createObjectURL(blob));
    } catch {
      setLogoObjectUrl(null);
    }
  }

  async function ladeVorschauPdf(f: FormState) {
    setPreviewStatus("loading");
    try {
      const blob = await previewRechnungsvorlage(accessToken, {
        vorlage: f.rechnungsvorlage,
        akzentfarbe: f.akzentfarbe,
        fusszeile_text: f.fusszeile_text,
        design_variante: f.design_variante,
        logo_groesse: f.logo_groesse,
        sprache: f.sprache,
        briefpapier_id: f.briefpapier_id || null,
        iban: f.iban,
        bic: f.bic,
        zeige_absenderzeile: f.zeige_absenderzeile,
        zeige_kundennummer: f.zeige_kundennummer,
        zeige_kontaktperson: f.zeige_kontaktperson,
        zeige_artikelnummer: f.zeige_artikelnummer,
        zeige_positionsbeschreibung: f.zeige_positionsbeschreibung,
        zeige_ust_pro_position: f.zeige_ust_pro_position,
        zeige_girocode: f.zeige_girocode,
        zeige_fusszeile: f.zeige_fusszeile,
        zeige_seitenzahlen: f.zeige_seitenzahlen,
        zeige_falz_lochmarken: f.zeige_falz_lochmarken,
      });
      setPreviewUrl((bisher) => {
        if (bisher) URL.revokeObjectURL(bisher);
        return URL.createObjectURL(blob);
      });
      setPreviewStatus("idle");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Vorschau konnte nicht geladen werden.");
      setPreviewStatus("error");
    }
  }

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      const mandant = await getMandant(accessToken);
      const briefpapiere = await listBriefpapier(accessToken);
      const naechsteForm = toForm(mandant);
      setForm(naechsteForm);
      setHatLogo(mandant.hat_logo);
      setBriefpapierListe(briefpapiere);
      await ladeLogoVorschau(mandant);
      await ladeVorschauPdf(naechsteForm);
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Rechnungsdesign konnte nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => {
    load();
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (logoObjectUrl) URL.revokeObjectURL(logoObjectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  function aktualisiere(patch: Partial<FormState>) {
    setForm((prev) => {
      const next = { ...prev, ...patch };
      ladeVorschauPdf(next);
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaveStatus("saving");
    setError("");
    try {
      const mandant = await mitBestaetigung(accessToken, "iban_aendern", (h) => updateMandant(accessToken, {
        rechnungsvorlage: form.rechnungsvorlage,
        akzentfarbe: form.akzentfarbe,
        fusszeile_text: form.fusszeile_text,
        design_variante: form.design_variante,
        logo_groesse: form.logo_groesse,
        briefpapier_id: form.briefpapier_id || null,
        sprache: form.sprache,
        iban: form.iban,
        bic: form.bic,
        zeige_absenderzeile: form.zeige_absenderzeile,
        zeige_kundennummer: form.zeige_kundennummer,
        zeige_kontaktperson: form.zeige_kontaktperson,
        zeige_artikelnummer: form.zeige_artikelnummer,
        zeige_positionsbeschreibung: form.zeige_positionsbeschreibung,
        zeige_ust_pro_position: form.zeige_ust_pro_position,
        zeige_girocode: form.zeige_girocode,
        zeige_fusszeile: form.zeige_fusszeile,
        zeige_seitenzahlen: form.zeige_seitenzahlen,
        zeige_falz_lochmarken: form.zeige_falz_lochmarken,
      }, h));
      setForm(toForm(mandant));
      setSaveStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Rechnungsdesign konnte nicht gespeichert werden.");
      setSaveStatus("error");
    }
  }

  async function handleLogoUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setLogoStatus("busy");
    setError("");
    try {
      const mandant = await uploadLogo(accessToken, file);
      setHatLogo(mandant.hat_logo);
      await ladeLogoVorschau(mandant);
      await ladeVorschauPdf(form);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Logo konnte nicht hochgeladen werden.");
    } finally {
      setLogoStatus("idle");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleLogoDelete() {
    setLogoStatus("busy");
    setError("");
    try {
      const mandant = await deleteLogo(accessToken);
      setHatLogo(mandant.hat_logo);
      setLogoObjectUrl(null);
      await ladeVorschauPdf(form);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Logo konnte nicht entfernt werden.");
    } finally {
      setLogoStatus("idle");
    }
  }

  async function handleBriefpapierUpload() {
    const file = briefpapierFileRef.current?.files?.[0];
    if (!file) return;
    setBriefpapierStatus("busy");
    setError("");
    try {
      const briefpapier = await uploadBriefpapier(accessToken, briefpapierName || "Briefpapier", file);
      setBriefpapierListe((prev) => [...prev, briefpapier].sort((a, b) => a.name.localeCompare(b.name)));
      setBriefpapierName("");
      setBriefpapierUploadOffen(false);
      if (briefpapierFileRef.current) briefpapierFileRef.current.value = "";
      aktualisiere({ briefpapier_id: briefpapier.id });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Briefpapier konnte nicht hochgeladen werden.");
    } finally {
      setBriefpapierStatus("idle");
    }
  }

  async function handleBriefpapierDelete() {
    if (!form.briefpapier_id) return;
    setBriefpapierStatus("busy");
    setError("");
    try {
      await deleteBriefpapier(accessToken, form.briefpapier_id);
      setBriefpapierListe((prev) => prev.filter((b) => b.id !== form.briefpapier_id));
      aktualisiere({ briefpapier_id: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Briefpapier konnte nicht entfernt werden.");
    } finally {
      setBriefpapierStatus("idle");
    }
  }

  if (loadStatus === "loading") return <PageState label="Rechnungsdesign wird geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={load} />;
  return (
    <div className="vorlage-layout">
      <form className="panel" onSubmit={handleSubmit}>
        {error && <p className="auth-error" role="alert">{error}</p>}
        {saveStatus === "saved" && <p className="auth-hint" role="status">Gespeichert.</p>}

        <h2>Vorlage</h2>
        <p className="auth-hint">Wähle deinen Stil. Die Muster zeigen Beispielinhalte; deine Farben und Angaben siehst du in der Live-Vorschau.</p>
        <div className="vorlage-karten" role="radiogroup" aria-label="Rechnungsvorlage">
          {VORLAGEN.map((v) => (
            <label key={v.wert} className={`vorlage-karte${form.rechnungsvorlage === v.wert ? " vorlage-karte--aktiv" : ""}`}>
              <img className="vorlage-miniatur" src={`/invoice-designs/${v.wert}.png`} alt="" width="240" height="340" loading="lazy" />
              <input
                type="radio"
                name="rechnungsvorlage"
                value={v.wert}
                checked={form.rechnungsvorlage === v.wert}
                onChange={() => aktualisiere({ rechnungsvorlage: v.wert })}
              />
              <span>
                <strong>{v.label}</strong>
                <span className="vorlage-karte-beschreibung">{v.beschreibung}</span>
              </span>
            </label>
          ))}
        </div>

        <h2>Design-Variante</h2>
        <PillAuswahl legende="Design-Variante" optionen={VARIANTEN} wert={form.design_variante} onChange={(wert) => aktualisiere({ design_variante: wert })} />

        <h2>Akzentfarbe</h2>
        <div className="field-row">
          <div>
            <label htmlFor="vorlage-farbe">Farbe (bei Variante „Standard")</label>
            <div className="farb-eingabe">
              <input
                id="vorlage-farbe"
                type="color"
                value={form.akzentfarbe}
                onChange={(e) => setForm((prev) => ({ ...prev, akzentfarbe: e.target.value }))}
                onBlur={() => ladeVorschauPdf(form)}
              />
              <input
                aria-label="Akzentfarbe als Hex-Code"
                value={form.akzentfarbe}
                onChange={(e) => setForm((prev) => ({ ...prev, akzentfarbe: e.target.value }))}
                onBlur={() => ladeVorschauPdf(form)}
                pattern="^#[0-9A-Fa-f]{6}$"
                maxLength={7}
              />
            </div>
          </div>
        </div>

        <h2>Logo</h2>
        <div className="logo-verwaltung">
          {logoObjectUrl ? (
            <img src={logoObjectUrl} alt="Aktuelles Firmenlogo" className="logo-vorschau" />
          ) : (
            <p className="auth-hint">{hatLogo ? "Logo hinterlegt." : "Noch kein Logo hochgeladen."}</p>
          )}
          <div className="logo-aktionen">
            <input
              ref={fileInputRef}
              type="file"
              aria-label="Logo-Datei auswählen"
              accept="image/jpeg,image/png,image/webp"
              onChange={handleLogoUpload}
              disabled={logoStatus === "busy"}
            />
            {hatLogo && (
              <button type="button" className="auth-link danger" onClick={handleLogoDelete} disabled={logoStatus === "busy"}>
                Logo entfernen
              </button>
            )}
          </div>
          <PillAuswahl legende="Logo-Größe" optionen={LOGO_GROESSEN} wert={form.logo_groesse} onChange={(wert) => aktualisiere({ logo_groesse: wert })} />
        </div>

        <h2>Briefpapier</h2>
        <label htmlFor="vorlage-briefpapier">Hintergrund</label>
        <div className="field-row">
          <select
            id="vorlage-briefpapier"
            value={form.briefpapier_id}
            onChange={(e) => aktualisiere({ briefpapier_id: e.target.value })}
          >
            <option value="">Ohne Briefpapier</option>
            {briefpapierListe.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          {form.briefpapier_id && (
            <button type="button" className="auth-link danger" onClick={handleBriefpapierDelete} disabled={briefpapierStatus === "busy"}>
              Löschen
            </button>
          )}
        </div>
        {briefpapierUploadOffen ? (
          <div className="confirm-row">
            <label htmlFor="vorlage-briefpapier-name">Name</label>
            <input
              id="vorlage-briefpapier-name"
              value={briefpapierName}
              onChange={(e) => setBriefpapierName(e.target.value)}
              placeholder="z.B. Geschäftspapier 2026"
            />
            <input ref={briefpapierFileRef} type="file" aria-label="Briefpapier-Datei auswählen" accept="image/jpeg,image/png,image/webp" />
            <div className="actions">
              <button type="button" disabled={briefpapierStatus === "busy"} onClick={handleBriefpapierUpload}>
                {briefpapierStatus === "busy" ? "Wird hochgeladen …" : "Hochladen"}
              </button>
              <button type="button" className="auth-link" onClick={() => setBriefpapierUploadOffen(false)}>Abbrechen</button>
            </div>
          </div>
        ) : (
          <button type="button" className="auth-link" onClick={() => setBriefpapierUploadOffen(true)}>+ Neu erstellen</button>
        )}

        <h2>Sprache</h2>
        <PillAuswahl legende="Sprache" optionen={SPRACHEN} wert={form.sprache} onChange={(wert) => aktualisiere({ sprache: wert })} />

        <h2>Elemente</h2>
        <div className="toggle-grid">
          {ELEMENTE.map((el) => (
            <label key={el.feld} className="checkbox-row">
              <input
                type="checkbox"
                checked={form[el.feld]}
                onChange={(e) => aktualisiere({ [el.feld]: e.target.checked } as Partial<FormState>)}
              />
              {el.label}
            </label>
          ))}
        </div>

        <h2>Bankverbindung</h2>
        <p className="auth-hint">Für den GiroCode (QR-Zahlungscode) auf der Rechnung.</p>
        {bankdatenSchreibgeschuetzt && <p className="auth-hint" role="status">Die Bankverbindung darf nur der Inhaber des Kontos ändern, weil sie auf jeder Rechnung steht.</p>}
        <div className="field-row">
          <div>
            <label htmlFor="vorlage-iban">IBAN</label>
            <input id="vorlage-iban" value={form.iban} maxLength={34} readOnly={bankdatenSchreibgeschuetzt} onChange={(e) => setForm((prev) => ({ ...prev, iban: e.target.value }))} onBlur={() => ladeVorschauPdf(form)} />
          </div>
          <div>
            <label htmlFor="vorlage-bic">BIC</label>
            <input id="vorlage-bic" value={form.bic} maxLength={11} readOnly={bankdatenSchreibgeschuetzt} onChange={(e) => setForm((prev) => ({ ...prev, bic: e.target.value }))} onBlur={() => ladeVorschauPdf(form)} />
          </div>
        </div>

        <h2>Fußzeile</h2>
        <label htmlFor="vorlage-fusszeile">Freitext (z.B. Bankverbindung, AGB-Hinweis)</label>
        <textarea
          id="vorlage-fusszeile"
          rows={4}
          maxLength={2000}
          value={form.fusszeile_text}
          onChange={(e) => setForm((prev) => ({ ...prev, fusszeile_text: e.target.value }))}
          onBlur={() => ladeVorschauPdf(form)}
        />

        <button type="submit" disabled={saveStatus === "saving"}>
          {saveStatus === "saving" ? "Wird gespeichert …" : "Speichern"}
        </button>
      </form>

      <div className="vorlage-vorschau panel">
        <h2>Vorschau</h2>
        <p className="auth-hint">Beispieldaten — deine echten Dokumente übernehmen dasselbe Design.</p>
        <PdfPreviewFrame
          title="Vorschau des Rechnungsdesigns"
          url={previewUrl}
          loading={previewStatus === "loading"}
          fehler={previewStatus === "error"}
          zoom={zoom}
          onZoomChange={setZoom}
        />
      </div>
    </div>
  );
}
