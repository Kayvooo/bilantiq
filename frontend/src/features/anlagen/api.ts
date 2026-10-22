import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}`, ...init?.headers },
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

export interface AfaPlanEintrag {
  jahr: number;
  afa_betrag: string;
  restbuchwert_ende: string;
}

export interface Anlage {
  id: string;
  bezeichnung: string;
  anschaffungsdatum: string;
  anschaffungskosten_netto: string;
  nutzungsdauer_jahre: number;
  kategorie: string | null;
  ist_gwg: boolean;
  afa_plan: AfaPlanEintrag[];
}

export interface AnlagenUebersicht {
  anlagen: Anlage[];
  afa_gesamt_jahr: string;
  jahr: number;
  hinweis: string;
}

export const getAnlagen = (accessToken: string, jahr: number) => requestJson<AnlagenUebersicht>(`/anlagen?jahr=${jahr}`, accessToken);

export const createAnlage = (accessToken: string, anlage: { bezeichnung: string; anschaffungsdatum: string; anschaffungskosten_netto: string; nutzungsdauer_jahre: number; kategorie: string | null }) =>
  requestJson<Anlage>("/anlagen", accessToken, { method: "POST", body: JSON.stringify(anlage) });
