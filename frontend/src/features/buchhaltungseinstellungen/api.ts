import { extractErrorDetail } from "../../lib/apiError";
import { ApiError } from "../auth/api";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(accessToken: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/buchhaltungseinstellungen`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Einstellungen konnten nicht geladen werden."));
  }
  return body as T;
}

export interface Buchhaltungseinstellungen {
  standard_zahlungsziel_tage: number;
  standard_ust_satz: string;
  kleinunternehmer: boolean;
}

export const DEFAULT_BUCHHALTUNGSEINSTELLUNGEN: Buchhaltungseinstellungen = {
  standard_zahlungsziel_tage: 14,
  standard_ust_satz: "19.00",
  kleinunternehmer: false,
};

export const getBuchhaltungseinstellungen = (accessToken: string) =>
  requestJson<Buchhaltungseinstellungen>(accessToken);

export const putBuchhaltungseinstellungen = (
  accessToken: string,
  einstellungen: Buchhaltungseinstellungen,
) => requestJson<Buchhaltungseinstellungen>(accessToken, {
  method: "PUT",
  body: JSON.stringify(einstellungen),
});

export function ustSatzFuerNeuePosition(einstellungen: Buchhaltungseinstellungen): string {
  return einstellungen.kleinunternehmer ? "0.00" : einstellungen.standard_ust_satz;
}
