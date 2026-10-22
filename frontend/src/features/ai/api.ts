import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import type { InvoiceDraft } from "../invoices/api";
import type { QuoteDraft } from "../quotes/api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(accessToken: string) {
  return { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
}

async function requestJson<T>(path: string, accessToken: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: authHeaders(accessToken),
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, extractErrorDetail(data, "KI-Anfrage ist fehlgeschlagen."));
  }
  return data as T;
}

export interface AssistantResponse {
  antwort: string;
  tool: string;
}

export const askAssistant = (accessToken: string, frage: string, jahr?: number) =>
  requestJson<AssistantResponse>("/ai/assistent", accessToken, { frage, jahr: jahr ?? null });

export const createInvoiceDraftSuggestion = (accessToken: string, anweisung: string) =>
  requestJson<InvoiceDraft>("/ai/rechnungsentwurf", accessToken, { anweisung });

export const createQuoteDraftSuggestion = (accessToken: string, anweisung: string) =>
  requestJson<QuoteDraft>("/ai/angebotsentwurf", accessToken, { anweisung });

export type TextArt = "rechnung" | "angebot" | "mahnung";
export type TextTon = "freundlich" | "neutral" | "bestimmt";

export const createTextSuggestion = (
  accessToken: string,
  payload: { art: TextArt; objekt_id: string; ton: TextTon; hinweis?: string },
) => requestJson<{ text: string }>("/ai/textvorschlag", accessToken, payload);
