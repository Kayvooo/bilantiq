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

export interface Produkt {
  id: string;
  bezeichnung: string;
  beschreibung: string | null;
  einzelpreis: string;
  ust_satz: string;
  einheit: string;
  aktiv: boolean;
  lagerbestand_aktiv: boolean;
  lagerbestand: string | null;
  artikelnummer?: string | null;
}

export type ProduktPayload = Omit<Produkt, "id" | "lagerbestand">;

export interface Lagerbewegung {
  id: string;
  produkt_id: string;
  datum: string;
  typ: "zugang" | "abgang";
  menge: string;
  grund: string;
}

export type LagerbewegungPayload = Omit<Lagerbewegung, "id" | "produkt_id">;

export const listProdukte = (accessToken: string) =>
  requestJson<Produkt[]>("/produkte", accessToken);

export const createProdukt = (accessToken: string, produkt: ProduktPayload) =>
  requestJson<Produkt>("/produkte", accessToken, {
    method: "POST",
    body: JSON.stringify(produkt),
  });

export const updateProdukt = (accessToken: string, produktId: string, updates: Partial<ProduktPayload>) =>
  requestJson<Produkt>(`/produkte/${produktId}`, accessToken, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });

export const listLagerbewegungen = (accessToken: string, produktId: string) =>
  requestJson<Lagerbewegung[]>(`/produkte/${produktId}/lagerbewegungen`, accessToken);

export const createLagerbewegung = (accessToken: string, produktId: string, bewegung: LagerbewegungPayload) =>
  requestJson<Lagerbewegung>(`/produkte/${produktId}/lagerbewegungen`, accessToken, {
    method: "POST",
    body: JSON.stringify(bewegung),
  });
