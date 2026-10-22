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

export interface KassenbuchEintrag {
  id: string;
  datum: string;
  typ: "einnahme" | "ausgabe";
  betrag: string;
  beschreibung: string;
  saldo_nach_buchung: string;
  erstellt_am: string;
}

export interface KassenbuchUebersicht {
  eintraege: KassenbuchEintrag[];
  aktueller_kassenbestand: string;
}

export const getKassenbuch = (accessToken: string) => requestJson<KassenbuchUebersicht>("/kassenbuch", accessToken);

export const createKassenbuchEintrag = (accessToken: string, eintrag: { datum: string; typ: "einnahme" | "ausgabe"; betrag: string; beschreibung: string }) =>
  requestJson<KassenbuchEintrag>("/kassenbuch", accessToken, { method: "POST", body: JSON.stringify(eintrag) });
