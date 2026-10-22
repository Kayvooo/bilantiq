import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface Schritt {
  id: string;
  titel: string;
  beschreibung: string;
  erledigt: boolean;
  ziel: string;
  optional: boolean;
  hinweis: string | null;
}

export interface ErsteSchritte {
  schritte: Schritt[];
  erledigt: number;
  gesamt: number;
}

export async function getErsteSchritte(accessToken: string): Promise<ErsteSchritte> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/erste-schritte`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Die Checkliste konnte nicht geladen werden."));
  }
  return body as ErsteSchritte;
}
