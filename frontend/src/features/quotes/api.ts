import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import type { InvoicePosition } from "../invoices/api";
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

export interface Quote {
  id: string;
  kontakt_id: string;
  nummer: string | null;
  status: "entwurf" | "versendet" | "angenommen" | "abgelehnt";
  anzeige_status: string;
  gueltig_bis: string;
  waehrung: string;
  netto_gesamt: string;
  ust_gesamt: string;
  brutto_gesamt: string;
  umgewandelt_in_invoice_id: string | null;
  positionen: InvoicePosition[];
  email_versendet_am: string | null;
  kontakt_email_vorhanden: boolean;
}

export interface QuoteDraft {
  kontakt_id: string;
  gueltig_bis: string;
  waehrung: string;
  positionen: InvoicePosition[];
}

export const listQuotes = (accessToken: string) => requestJson<Quote[]>("/angebote", accessToken);

export const createQuote = (accessToken: string, draft: QuoteDraft) =>
  requestJson<Quote>("/angebote", accessToken, { method: "POST", body: JSON.stringify(draft) });

export const sendQuote = (accessToken: string, id: string) =>
  requestJson<Quote>(`/angebote/${id}/versenden`, accessToken, { method: "POST" });

// Bewusst nicht .../versenden -- dieser Pfad finalisiert den Entwurf (sendQuote oben:
// vergibt die Angebotsnummer, setzt status="versendet"), unabhaengig davon ob je
// gemailt wurde. Dies hier verschickt tatsaechlich eine E-Mail mit PDF-Anhang.
export const sendeAngebot = (accessToken: string, id: string, text?: string) =>
  requestJson<Quote>(`/angebote/${id}/per-email-senden`, accessToken, {
    method: "POST",
    body: JSON.stringify({ text: text ?? null }),
  });

export const acceptQuote = (accessToken: string, id: string) =>
  requestJson<Quote>(`/angebote/${id}/annehmen`, accessToken, { method: "POST" });

export const rejectQuote = (accessToken: string, id: string) =>
  requestJson<Quote>(`/angebote/${id}/ablehnen`, accessToken, { method: "POST" });

export const convertQuoteToInvoice = (accessToken: string, id: string) =>
  requestJson<{ invoice_id: string; status: string }>(`/angebote/${id}/in-rechnung-umwandeln`, accessToken, { method: "POST" });

export async function downloadQuotePdf(accessToken: string, id: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/angebote/${id}/pdf`, { headers: authHeaders(accessToken) });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, "PDF konnte nicht geladen werden.");
  }
  return response.blob();
}
