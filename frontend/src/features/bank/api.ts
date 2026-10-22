import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit, json = true): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(json ? { "Content-Type": "application/json" } : {}),
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

export interface CsvProfil {
  datum: string;
  datum_format: string;
  dezimal: "komma" | "punkt";
  betrag: string | null;
  soll: string | null;
  haben: string | null;
  name: string | null;
  iban: string | null;
  verwendungszweck: string[];
  wertstellung: string | null;
  waehrung: string | null;
  trennzeichen: string | null;
  kodierung: string | null;
}

export interface Bankkonto {
  id: string;
  bezeichnung: string;
  iban: string | null;
  csv_profil: CsvProfil | null;
  anzahl_umsaetze: number;
}

export interface CsvVorschau {
  kopfzeilen: string[];
  beispielzeilen: string[][];
  anzahl_zeilen: number;
  trennzeichen: string;
  kodierung: string;
  vorgeschlagenes_profil: CsvProfil | null;
}

export interface ImportVorschau {
  format: "camt" | "csv";
  anzahl: number;
  zeitraum_von: string | null;
  zeitraum_bis: string | null;
  beispiele: Record<string, string>[];
  csv: CsvVorschau | null;
  gespeichertes_profil: CsvProfil | null;
}

export interface ImportErgebnis {
  import_id: string;
  format: "camt" | "csv";
  neu: number;
  doppelt: number;
  zeitraum_von: string | null;
  zeitraum_bis: string | null;
}

export interface Vorschlag {
  typ: "rechnung" | "altrechnung" | "beleg" | "ausgabe";
  ziel_id: string;
  anzeige: string;
  score: number;
  sicher: boolean;
  gruende: string[];
}

export interface Umsatz {
  id: string;
  bankkonto_id: string;
  buchungsdatum: string;
  wertstellung: string | null;
  betrag: string;
  gegenpartei_name: string | null;
  gegenpartei_iban: string | null;
  verwendungszweck: string;
  status: "offen" | "zugeordnet" | "ignoriert";
  zuordnung_typ: "rechnung" | "altrechnung" | "beleg" | "ausgabe" | null;
  zuordnung_id: string | null;
  ignoriert_grund: string | null;
  beleg_fehlt: boolean;
  vorschlag: Vorschlag | null;
}

export interface Zusammenfassung {
  offen: number;
  beleg_fehlt: number;
  sichere_vorschlaege: number;
  zugeordnet: number;
  ignoriert: number;
}

export type UmsatzFilter = "offen" | "beleg_fehlt" | "zugeordnet" | "ignoriert";

export const listKonten = (accessToken: string) => requestJson<Bankkonto[]>("/bank/konten", accessToken);

export const createKonto = (accessToken: string, bezeichnung: string, iban: string) =>
  requestJson<Bankkonto>("/bank/konten", accessToken, {
    method: "POST",
    body: JSON.stringify({ bezeichnung, iban: iban.trim() || null }),
  });

function dateiForm(file: File, profil?: CsvProfil | null): FormData {
  const form = new FormData();
  form.append("file", file);
  if (profil) form.append("profil", JSON.stringify(profil));
  return form;
}

export const importVorschau = (accessToken: string, kontoId: string, file: File) =>
  requestJson<ImportVorschau>(
    `/bank/konten/${kontoId}/import/vorschau`, accessToken, { method: "POST", body: dateiForm(file) }, false,
  );

export const importiereAuszug = (accessToken: string, kontoId: string, file: File, profil?: CsvProfil | null) =>
  requestJson<ImportErgebnis>(
    `/bank/konten/${kontoId}/import`, accessToken, { method: "POST", body: dateiForm(file, profil) }, false,
  );

export const listUmsaetze = (accessToken: string, filter: UmsatzFilter) =>
  requestJson<{ umsaetze: Umsatz[]; gesamt: number }>(`/bank/umsaetze?status=${filter}&limit=200`, accessToken);

export const getZusammenfassung = (accessToken: string) => requestJson<Zusammenfassung>("/bank/zusammenfassung", accessToken);

export const ordneZu = (accessToken: string, umsatzId: string, typ: Vorschlag["typ"], zielId: string) =>
  requestJson<Umsatz>(`/bank/umsaetze/${umsatzId}/zuordnen`, accessToken, {
    method: "POST",
    body: JSON.stringify({ typ, ziel_id: zielId }),
  });

export const ignoriereUmsatz = (accessToken: string, umsatzId: string, grund: string) =>
  requestJson<Umsatz>(`/bank/umsaetze/${umsatzId}/ignorieren`, accessToken, {
    method: "POST",
    body: JSON.stringify({ grund }),
  });

export const hebeZuordnungAuf = (accessToken: string, umsatzId: string) =>
  requestJson<Umsatz>(`/bank/umsaetze/${umsatzId}/zuordnung-aufheben`, accessToken, { method: "POST" });

export const bestaetigeSichere = (accessToken: string, umsatzIds: string[]) =>
  requestJson<{ bestaetigt: number; uebersprungen: { umsatz_id: string; grund: string }[] }>(
    "/bank/zuordnungen/bestaetigen", accessToken, { method: "POST", body: JSON.stringify({ umsatz_ids: umsatzIds }) },
  );
