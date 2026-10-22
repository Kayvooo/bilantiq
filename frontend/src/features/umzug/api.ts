import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface UmzugSchritt {
  id: string;
  titel: string;
  beschreibung: string;
  status: "erledigt" | "offen" | "nicht_noetig" | "info";
  detail: string | null;
  /** Seite im Frontend (DesktopStep); null = nur ein Hinweis */
  ziel: string | null;
  aktion: "neu" | "import" | null;
  ansicht: "altsystem" | null;
  nur_inhaber: boolean;
  optional: boolean;
  hinweis: string | null;
}

export interface Umzug {
  schritte: UmzugSchritt[];
  erledigt: number;
  gesamt: number;
}

export async function getUmzug(accessToken: string): Promise<Umzug> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/umzug`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Umzug;
}
