import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(accessToken: string) {
  return { Authorization: `Bearer ${accessToken}` };
}

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers: { ...authHeaders(accessToken), ...init?.headers } });
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

export interface FieldValue {
  wert: string | null;
  confidence: number | null;
  unklar: boolean;
}

export interface Receipt {
  id: string;
  status: "neu" | "geprueft" | "unklar" | "gebucht";
  hochgeladen_am: string;
  betrag: FieldValue;
  datum: FieldValue;
  anbieter: FieldValue;
  ust_satz: FieldValue;
  kategorie_vorschlag: FieldValue;
  begruendung: string | null;
  buchungskonto_vorschlag: string | null;
  gebucht_als: string | null;
  ist_duplikat: boolean;
  duplikat_von: string | null;
  beleg_typ: "ocr" | "xrechnung" | "zugferd";
  rechnungsnummer: string | null;
  faelligkeit: string | null;
  iban: string | null;
  steueranteile_vorschlag: { ust_satz: string; bruttobetrag: string }[] | null;
  hinweise: string[];
  zahlungsdatum_vorschlag: string | null;
}

export async function uploadBeleg(accessToken: string, file: File, force = false): Promise<Receipt> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("force", force ? "true" : "false");
  return requestJson<Receipt>("/belege", accessToken, { method: "POST", body: formData });
}

export const listBelege = (accessToken: string) => requestJson<Receipt[]>("/belege", accessToken);

export async function fetchBelegDatei(accessToken: string, belegId: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/belege/${belegId}/datei`, { headers: authHeaders(accessToken) });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(body, "Originalbeleg konnte nicht geladen werden."));
  }
  return response.blob();
}

export interface Steueranteil {
  ust_satz: string;
  bruttobetrag: string;
}

export const deleteBeleg = (accessToken: string, belegId: string) =>
  requestJson<void>(`/belege/${belegId}`, accessToken, { method: "DELETE" });

export interface Lernvorschlag {
  gefunden: boolean;
  kategorie: string | null;
  konto: string | null;
  ust_satz: string | null;
  confidence: number | null;
  begruendung: string | null;
}

export const ladeLernvorschlag = (accessToken: string, anbieter: string) =>
  requestJson<Lernvorschlag>(`/belege/vorschlag?anbieter=${encodeURIComponent(anbieter)}`, accessToken);

export interface Bestaetigung {
  betrag?: string;
  datum?: string;
  zahlungsdatum?: string;
  anbieter?: string;
  ust_satz?: string;
  steueranteile?: Steueranteil[];
  kategorie?: string;
  konto?: string;
}

export const bestaetigeBeleg = (accessToken: string, belegId: string, angaben: Bestaetigung) =>
  requestJson(`/belege/${belegId}/bestaetigen`, accessToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(angaben),
  });

export interface Ausgabe {
  id: string;
  receipt_id: string | null;
  betrag: string;
  datum: string;
  zahlungsdatum: string;
  anbieter: string;
  ust_satz: string | null;
  steueranteile: Steueranteil[];
  kategorie: string;
  konto: string;
}

export const listAusgaben = (accessToken: string) => requestJson<Ausgabe[]>("/ausgaben", accessToken);

export interface WiederkehrendeAusgabe {
  id: string;
  bezeichnung: string;
  anbieter: string;
  betrag: string;
  ust_satz: string;
  kategorie: string;
  intervall: "monatlich" | "quartalsweise" | "jaehrlich";
  naechstes_datum: string;
  enddatum: string | null;
  aktiv: boolean;
}

export interface WiederkehrendeAusgabeDraft {
  bezeichnung: string;
  anbieter: string;
  betrag: string;
  ust_satz: string;
  kategorie: string;
  intervall: "monatlich" | "quartalsweise" | "jaehrlich";
  naechstes_datum: string;
  enddatum: string | null;
}

export interface AusgabenErzeugungsErgebnis {
  erzeugte_ausgaben: string[];
  anzahl: number;
}

const jsonInit = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
});

export const listWiederkehrendeAusgaben = (accessToken: string) =>
  requestJson<WiederkehrendeAusgabe[]>("/wiederkehrende-ausgaben", accessToken);

export const createWiederkehrendeAusgabe = (accessToken: string, draft: WiederkehrendeAusgabeDraft) =>
  requestJson<WiederkehrendeAusgabe>("/wiederkehrende-ausgaben", accessToken, jsonInit("POST", draft));

export const deaktiviereWiederkehrendeAusgabe = (accessToken: string, id: string) =>
  requestJson<WiederkehrendeAusgabe>(`/wiederkehrende-ausgaben/${id}/deaktivieren`, accessToken, jsonInit("POST"));

export const erzeugeFaelligeAusgaben = (accessToken: string) =>
  requestJson<AusgabenErzeugungsErgebnis>("/wiederkehrende-ausgaben/erzeugen", accessToken, jsonInit("POST"));
