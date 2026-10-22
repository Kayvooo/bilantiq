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
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as T;
}

export interface AuftragsbestaetigungPosition {
  id: string;
  beschreibung: string;
  menge: string;
  einzelpreis: string;
  ust_satz: string;
}

export interface Auftragsbestaetigung {
  id: string;
  quote_id: string;
  kontakt_id: string;
  nummer: string;
  waehrung: string;
  netto_gesamt: string;
  ust_gesamt: string;
  brutto_gesamt: string;
  erstellt_am: string;
  positionen: AuftragsbestaetigungPosition[];
}

export interface LieferscheinPosition {
  id: string;
  beschreibung: string;
  menge: string;
}

export interface LieferscheinPositionDraft {
  beschreibung: string;
  menge: string;
}

export interface Lieferschein {
  id: string;
  auftragsbestaetigung_id: string;
  kontakt_id: string;
  nummer: string;
  lieferdatum: string;
  erstellt_am: string;
  positionen: LieferscheinPosition[];
}

export const listAuftragsbestaetigungen = (accessToken: string) =>
  requestJson<Auftragsbestaetigung[]>("/auftragsbestaetigungen", accessToken);

export const createAuftragsbestaetigung = (accessToken: string, quoteId: string) =>
  requestJson<Auftragsbestaetigung>("/auftragsbestaetigungen", accessToken, {
    method: "POST",
    body: JSON.stringify({ quote_id: quoteId }),
  });

export async function downloadAuftragsbestaetigungPdf(accessToken: string, id: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/auftragsbestaetigungen/${id}/pdf`, { headers: authHeaders(accessToken) });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, "PDF konnte nicht geladen werden.");
  }
  return response.blob();
}

export const listLieferscheine = (accessToken: string) => requestJson<Lieferschein[]>("/lieferscheine", accessToken);

export const createLieferschein = (
  accessToken: string,
  draft: { auftragsbestaetigung_id: string; lieferdatum: string; positionen: LieferscheinPositionDraft[] },
) => requestJson<Lieferschein>("/lieferscheine", accessToken, { method: "POST", body: JSON.stringify(draft) });

export async function downloadLieferscheinPdf(accessToken: string, id: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/lieferscheine/${id}/pdf`, { headers: authHeaders(accessToken) });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, "PDF konnte nicht geladen werden.");
  }
  return response.blob();
}
