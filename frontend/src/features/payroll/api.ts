import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function headers(accessToken: string) {
  return { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` };
}

async function request<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers: { ...headers(accessToken), ...init?.headers } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Lohnvorbereitung konnte nicht verarbeitet werden."));
  }
  return body as T;
}

export interface Mitarbeiter {
  id: string;
  personalnummer: string;
  vorname: string;
  nachname: string;
  eintrittsdatum: string;
  austrittsdatum: string | null;
  monatsbrutto: string;
  aktiv: boolean;
}

export interface MitarbeiterDraft {
  personalnummer: string;
  vorname: string;
  nachname: string;
  eintrittsdatum: string;
  austrittsdatum: string | null;
  monatsbrutto: string;
}

export interface MitarbeiterUpdate {
  vorname?: string;
  nachname?: string;
  eintrittsdatum?: string;
  austrittsdatum?: string | null;
  monatsbrutto?: string;
}

export interface Monatsentwurf {
  id: string;
  mitarbeiter_id: string;
  personalnummer: string;
  mitarbeiter_name: string;
  jahr: number;
  monat: number;
  grundbrutto: string;
  steuerpflichtige_zuschlaege: string;
  steuerfreie_erstattungen: string;
  sonstige_abzuege: string;
  gesamtbrutto: string;
  zwischenbetrag_vor_abgaben: string;
  status: "vorbereitung" | "abgeschlossen";
  abgeschlossen_am: string | null;
  verbindlicher_abschluss_verfuegbar: false;
  hinweis: string;
}

export interface MonatsentwurfDraft {
  mitarbeiter_id: string;
  jahr: number;
  monat: number;
  grundbrutto: string | null;
  steuerpflichtige_zuschlaege: string;
  steuerfreie_erstattungen: string;
  sonstige_abzuege: string;
}

export interface MonatsentwurfUpdate {
  grundbrutto?: string;
  steuerpflichtige_zuschlaege?: string;
  steuerfreie_erstattungen?: string;
  sonstige_abzuege?: string;
}

export const listMitarbeitende = (token: string) => request<Mitarbeiter[]>("/lohn/mitarbeitende", token);
export const createMitarbeiter = (token: string, draft: MitarbeiterDraft) => request<Mitarbeiter>("/lohn/mitarbeitende", token, { method: "POST", body: JSON.stringify(draft) });
export const updateMitarbeiter = (token: string, id: string, updates: MitarbeiterUpdate) => request<Mitarbeiter>(`/lohn/mitarbeitende/${id}`, token, { method: "PATCH", body: JSON.stringify(updates) });
export const deactivateMitarbeiter = (token: string, id: string) => request<Mitarbeiter>(`/lohn/mitarbeitende/${id}/deaktivieren`, token, { method: "POST" });
export const reactivateMitarbeiter = (token: string, id: string) => request<Mitarbeiter>(`/lohn/mitarbeitende/${id}/reaktivieren`, token, { method: "POST" });
export const listMonatsentwuerfe = (token: string, jahr: number, monat: number) => request<Monatsentwurf[]>(`/lohn/monatsentwuerfe?jahr=${jahr}&monat=${monat}`, token);
export const createMonatsentwurf = (token: string, draft: MonatsentwurfDraft) => request<Monatsentwurf>("/lohn/monatsentwuerfe", token, { method: "POST", body: JSON.stringify(draft) });
export const updateMonatsentwurf = (token: string, id: string, updates: MonatsentwurfUpdate) => request<Monatsentwurf>(`/lohn/monatsentwuerfe/${id}`, token, { method: "PATCH", body: JSON.stringify(updates) });
export const abschliessenMonatsentwurf = (token: string, id: string) => request<Monatsentwurf>(`/lohn/monatsentwuerfe/${id}/abschliessen`, token, { method: "POST" });
export const reaktivierenMonatsentwurf = (token: string, id: string) => request<Monatsentwurf>(`/lohn/monatsentwuerfe/${id}/reaktivieren`, token, { method: "POST" });

export async function downloadMonthExport(token: string, jahr: number, monat: number): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/lohn/monate/${jahr}/${monat}/export`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, "Arbeitsdatei konnte nicht erstellt werden.");
  }
  return response.blob();
}

export async function downloadLohnzettel(token: string, entwurfId: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/lohn/monatsentwuerfe/${entwurfId}/lohnzettel`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new ApiError(response.status, "Lohnzettel konnte nicht erstellt werden.");
  return response.blob();
}
