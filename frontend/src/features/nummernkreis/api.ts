import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface Nummernkreis {
  jahr: number;
  naechste_nummer: number;
  naechste_rechnungsnummer: string;
  hoechste_bilantiq: number;
  hoechste_altsystem: number | null;
  /** kleinster Wert, auf den sich die naechste Nummer setzen laesst */
  mindestens: number;
  /** die naechste Bilantiq-Nummer waere im alten Programm schon vergeben */
  kollision: boolean;
  vorschlag: number | null;
}

async function anfrage(accessToken: string, init?: RequestInit): Promise<Nummernkreis> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/einstellungen/nummernkreis`, {
      ...init, headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Nummernkreis;
}

export const getNummernkreis = (accessToken: string) => anfrage(accessToken);

export const setzeNummernkreis = (accessToken: string, naechsteNummer: number) =>
  anfrage(accessToken, { method: "PUT", body: JSON.stringify({ naechste_nummer: naechsteNummer }) });
