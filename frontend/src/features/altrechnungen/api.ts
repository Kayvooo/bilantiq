import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function anfrage(path: string, accessToken: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers: { Authorization: `Bearer ${accessToken}`, ...init?.headers } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return response;
}

const json = async <T>(path: string, accessToken: string, init?: RequestInit) => (await anfrage(path, accessToken, init)).json() as Promise<T>;

export type AltStatus = "offen" | "ueberfaellig" | "bezahlt";

export interface AltZahlung {
  id: string;
  datum: string;
  betrag: string;
  quelle: "manuell" | "bankabgleich";
}

export interface Altrechnung {
  id: string;
  nummer: string;
  kontakt_id: string;
  kontakt_name: string;
  rechnungsdatum: string;
  faelligkeit: string | null;
  brutto: string;
  offen_beim_import: string;
  offen: string;
  status: AltStatus;
  bezahlt_im_altsystem: boolean;
  bezahlt_im_altsystem_am: string | null;
  hat_pdf: boolean;
  zahlungen: AltZahlung[];
}

export interface AltrechnungListe {
  gesamt: number;
  eintraege: Altrechnung[];
}

export const listeAltrechnungen = (accessToken: string, optionen: { limit?: number } = {}) =>
  json<AltrechnungListe>(`/altrechnungen?limit=${optionen.limit ?? 2000}`, accessToken);

export const erfasseZahlung = (accessToken: string, id: string, zahlung: { datum?: string; betrag?: string }) =>
  json<Altrechnung>(`/altrechnungen/${id}/zahlung`, accessToken, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(zahlung),
  });

export interface PdfErgebnis {
  dateiname: string;
  status: "zugeordnet" | "unklar" | "keine" | "abgelehnt";
  altrechnung_id: string | null;
  nummer: string | null;
  grund: string | null;
}

export const ladePdfsHoch = (accessToken: string, dateien: File[]) => {
  const form = new FormData();
  for (const datei of dateien) form.append("files", datei);
  return json<{ ergebnisse: PdfErgebnis[] }>("/altrechnungen/pdfs", accessToken, { method: "POST", body: form });
};

export const ordnePdfZu = (accessToken: string, id: string, datei: File) => {
  const form = new FormData();
  form.append("file", datei);
  return json<Altrechnung>(`/altrechnungen/${id}/pdf`, accessToken, { method: "POST", body: form });
};

export const ladeAltPdf = async (accessToken: string, id: string) => (await anfrage(`/altrechnungen/${id}/pdf`, accessToken)).blob();

export interface HistorieEintrag {
  art: "bilantiq" | "altsystem";
  id: string;
  nummer: string | null;
  datum: string;
  brutto: string;
  offen: string;
  status: string;
}

export interface Historie {
  kontakt_id: string;
  eintraege: HistorieEintrag[];
  umsatz_brutto_bilantiq: string;
  umsatz_brutto_altsystem: string;
  offen_brutto: string;
}

export const ladeHistorie = (accessToken: string, kontaktId: string) => json<Historie>(`/kontakte/${kontaktId}/historie`, accessToken);
