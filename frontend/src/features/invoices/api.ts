import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(accessToken: string) {
  return { Authorization: `Bearer ${accessToken}` };
}

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...authHeaders(accessToken), ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const detail = extractErrorDetail(body, "Etwas ist schiefgelaufen.");
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

async function requestBlob(path: string, accessToken: string, init?: RequestInit): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...authHeaders(accessToken), ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return response.blob();
}

export interface Kontakt {
  id: string;
  name: string;
  strasse: string | null;
  plz: string | null;
  ort: string | null;
  land: string;
  ust_id: string | null;
  email: string | null;
  ist_geschaeftskunde: boolean;
  kundennummer?: string | null;
  typ?: KontaktTyp;
  anrede?: string | null;
  vorname?: string | null;
  nachname?: string | null;
  telefon?: string | null;
  notiz?: string | null;
  steuernummer?: string | null;
  iban?: string | null;
  bic?: string | null;
  zahlungsziel_tage?: number | null;
  skonto_prozent?: string | null;
  skonto_tage?: number | null;
  leitweg_id?: string | null;
  archiviert?: boolean;
}

export type KontaktTyp = "kunde" | "lieferant" | "beide";
export type KontaktEingabe = Omit<Kontakt, "id" | "archiviert">;

export interface InvoicePosition {
  id?: string;
  beschreibung: string;
  menge: string;
  einzelpreis: string;
  ust_satz: string;
  kategorie?: string | null;
  artikelnummer?: string | null;
}

export interface Invoice {
  id: string;
  kontakt_id: string;
  kontakt_name: string;
  nummer: string | null;
  status: "entwurf" | "final" | "storniert";
  anzeige_status: string;
  leistungsdatum: string;
  faelligkeitsdatum: string;
  waehrung: string;
  netto_gesamt: string;
  ust_gesamt: string;
  brutto_gesamt: string;
  e_invoice_format: string | null;
  korrigiert_invoice_id: string | null;
  bezahlt_am: string | null;
  positionen: InvoicePosition[];
  e_rechnung_hinweis: boolean;
  betreff: string | null;
  kopftext: string | null;
  fusstext: string | null;
  referenznummer: string | null;
  kostenstelle: string | null;
  zahlungsmethode: string | null;
  skonto_tage: number | null;
  skonto_prozent: string | null;
  interne_kontaktperson_user_id: string | null;
  versendet_am: string | null;
  kontakt_email_vorhanden: boolean;
}

export interface Positionskategorie {
  id: string;
  name: string;
}

export interface Mahnung {
  id: string;
  invoice_id: string;
  stufe: number;
  stufe_bezeichnung: string;
  mahngebuehr: string;
  neue_faelligkeit: string;
  erstellt_am: string;
  versendet_am: string | null;
  kontakt_email_vorhanden: boolean;
}

export interface MahnungUebersicht extends Mahnung {
  rechnung_nummer: string;
  kontakt_name: string;
  rechnung_brutto: string;
}

export const listKontakte = (accessToken: string, filter?: { typ?: "kunde" | "lieferant"; archiviert?: boolean }) => {
  const parameter = new URLSearchParams();
  if (filter?.typ) parameter.set("typ", filter.typ);
  if (filter?.archiviert) parameter.set("archiviert", "true");
  const query = parameter.toString();
  return requestJson<Kontakt[]>(`/kontakte${query ? `?${query}` : ""}`, accessToken);
};

export const createKontakt = (accessToken: string, kontakt: KontaktEingabe) =>
  requestJson<Kontakt>("/kontakte", accessToken, { method: "POST", body: JSON.stringify(kontakt) });

export const updateKontakt = (accessToken: string, kontaktId: string, updates: Partial<KontaktEingabe>) =>
  requestJson<Kontakt>(`/kontakte/${kontaktId}`, accessToken, { method: "PATCH", body: JSON.stringify(updates) });

export const archiviereKontakt = (accessToken: string, kontaktId: string) =>
  requestJson<Kontakt>(`/kontakte/${kontaktId}/archivieren`, accessToken, { method: "POST" });

export const stelleKontaktWiederHer = (accessToken: string, kontaktId: string) =>
  requestJson<Kontakt>(`/kontakte/${kontaktId}/wiederherstellen`, accessToken, { method: "POST" });

export const loescheKontakt = (accessToken: string, kontaktId: string) =>
  requestJson<null>(`/kontakte/${kontaktId}`, accessToken, { method: "DELETE" });

export const listInvoices = (accessToken: string) => requestJson<Invoice[]>("/invoices", accessToken);

export interface InvoiceDraft {
  kontakt_id: string;
  leistungsdatum: string;
  faelligkeitsdatum: string;
  waehrung: string;
  positionen: InvoicePosition[];
  betreff?: string;
  kopftext?: string;
  fusstext?: string;
  referenznummer?: string;
  kostenstelle?: string;
  zahlungsmethode?: string;
  skonto_tage?: number;
  skonto_prozent?: string;
  interne_kontaktperson_user_id?: string;
}

export const createInvoice = (accessToken: string, draft: InvoiceDraft) =>
  requestJson<Invoice>("/invoices", accessToken, { method: "POST", body: JSON.stringify(draft) });

export const previewInvoice = (accessToken: string, draft: InvoiceDraft) =>
  requestBlob("/invoices/vorschau", accessToken, { method: "POST", body: JSON.stringify(draft) });

export const listPositionskategorien = (accessToken: string) =>
  requestJson<Positionskategorie[]>("/positionskategorien", accessToken);

export const deletePositionskategorie = (accessToken: string, id: string) =>
  requestJson<void>(`/positionskategorien/${id}`, accessToken, { method: "DELETE" });

export const finalizeInvoice = (accessToken: string, invoiceId: string) =>
  requestJson<Invoice>(`/invoices/${invoiceId}/finalize`, accessToken, { method: "POST" });

export const stornoInvoice = (accessToken: string, invoiceId: string) =>
  requestJson<Invoice>(`/invoices/${invoiceId}/storno`, accessToken, { method: "POST" });

export const downloadInvoicePdf = (accessToken: string, invoiceId: string) =>
  requestBlob(`/invoices/${invoiceId}/pdf`, accessToken);

export const downloadXRechnung = (accessToken: string, invoiceId: string) =>
  requestBlob(`/invoices/${invoiceId}/e-rechnung`, accessToken, { method: "POST" });

export const downloadZugferdPdf = (accessToken: string, invoiceId: string) =>
  requestBlob(`/invoices/${invoiceId}/zugferd-pdf`, accessToken, { method: "POST" });

export const markInvoicePaid = (accessToken: string, invoiceId: string) =>
  requestJson<Invoice>(`/invoices/${invoiceId}/bezahlt`, accessToken, { method: "POST", body: JSON.stringify({}) });

export const sendeRechnung = (accessToken: string, invoiceId: string, text?: string) =>
  requestJson<Invoice>(`/invoices/${invoiceId}/versenden`, accessToken, {
    method: "POST",
    body: JSON.stringify({ text: text ?? null }),
  });

export const createMahnung = (accessToken: string, invoiceId: string) =>
  requestJson<Mahnung>(`/invoices/${invoiceId}/mahnung`, accessToken, { method: "POST" });

export const listMahnungen = (accessToken: string, invoiceId: string) =>
  requestJson<Mahnung[]>(`/invoices/${invoiceId}/mahnungen`, accessToken);

export const listAlleMahnungen = (accessToken: string) =>
  requestJson<MahnungUebersicht[]>("/mahnungen", accessToken);

export const sendeMahnung = (accessToken: string, mahnungId: string, text?: string) =>
  requestJson<Mahnung>(`/mahnungen/${mahnungId}/versenden`, accessToken, {
    method: "POST",
    body: JSON.stringify({ text: text ?? null }),
  });

export const downloadMahnungPdf = (accessToken: string, mahnungId: string) =>
  requestBlob(`/mahnungen/${mahnungId}/pdf`, accessToken);

export interface WiederkehrendeRechnung {
  id: string;
  kontakt_id: string;
  kontakt_name: string;
  bezeichnung: string;
  intervall: "monatlich" | "quartalsweise" | "jaehrlich";
  naechstes_datum: string;
  enddatum: string | null;
  aktiv: boolean;
  positionen: InvoicePosition[];
}

export interface WiederkehrendeRechnungDraft {
  kontakt_id: string;
  bezeichnung: string;
  intervall: "monatlich" | "quartalsweise" | "jaehrlich";
  naechstes_datum: string;
  enddatum: string | null;
  positionen: InvoicePosition[];
}

export interface ErzeugungsErgebnis {
  erzeugte_rechnungen: string[];
  anzahl: number;
}

export const listWiederkehrendeRechnungen = (accessToken: string) =>
  requestJson<WiederkehrendeRechnung[]>("/wiederkehrende-rechnungen", accessToken);

export const createWiederkehrendeRechnung = (accessToken: string, draft: WiederkehrendeRechnungDraft) =>
  requestJson<WiederkehrendeRechnung>("/wiederkehrende-rechnungen", accessToken, { method: "POST", body: JSON.stringify(draft) });

export const deaktiviereWiederkehrendeRechnung = (accessToken: string, id: string) =>
  requestJson<WiederkehrendeRechnung>(`/wiederkehrende-rechnungen/${id}/deaktivieren`, accessToken, { method: "POST" });

export const erzeugeFaelligeRechnungen = (accessToken: string) =>
  requestJson<ErzeugungsErgebnis>("/wiederkehrende-rechnungen/erzeugen", accessToken, { method: "POST" });
