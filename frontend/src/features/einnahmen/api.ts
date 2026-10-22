import { extractErrorDetail } from "../../lib/apiError";
import { ApiError } from "../auth/api";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
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
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as T;
}

export interface SonstigeEinnahme {
  id: string;
  bezeichnung: string;
  betrag_brutto: string;
  ust_satz: string;
  datum: string;
  verwendungszweck: string | null;
}

export type SonstigeEinnahmePayload = Omit<SonstigeEinnahme, "id">;

export const listEinnahmen = (accessToken: string) =>
  requestJson<SonstigeEinnahme[]>("/einnahmen", accessToken);

export const createEinnahme = (accessToken: string, einnahme: SonstigeEinnahmePayload) =>
  requestJson<SonstigeEinnahme>("/einnahmen", accessToken, {
    method: "POST",
    body: JSON.stringify(einnahme),
  });

export const updateEinnahme = (
  accessToken: string,
  einnahmeId: string,
  updates: Partial<SonstigeEinnahmePayload>,
) => requestJson<SonstigeEinnahme>(`/einnahmen/${einnahmeId}`, accessToken, {
  method: "PATCH",
  body: JSON.stringify(updates),
});
