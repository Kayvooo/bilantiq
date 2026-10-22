/**
 * API-Aufrufe für Passwort-Reset und MFA-Wiederherstellungscodes.
 *
 * Bewusst ein eigenes kleines Modul statt Ergänzungen in api.ts (dort ist `request` nicht exportiert): So bleibt api.ts
 * unberührt. Fehlerverhalten und Basis-URL entsprechen api.ts (gleiche ApiError-Klasse, gleiche 401-Behandlung).
 */
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";
import { ApiError, type SecurityOverview, type TokenResponse } from "./api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar. Bitte prüfe deine Verbindung.");
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as T;
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

/** Antwort von /security um die Zahl der noch gültigen Wiederherstellungscodes erweitert (null, solange MFA aus ist). */
export type SecurityOverviewMitCodes = SecurityOverview & { wiederherstellungscodes_offen?: number | null };

export interface WiederherstellungscodesAntwort {
  /** Nur bei der ersten Aktivierung gesetzt; wird nie wieder angezeigt. */
  wiederherstellungscodes: string[] | null;
}

export function passwortVergessen(email: string) {
  return request<{ detail: string }>("/auth/passwort/vergessen", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function passwortZuruecksetzen(token: string, neuesPasswort: string) {
  return request<void>("/auth/passwort/zuruecksetzen", {
    method: "POST",
    body: JSON.stringify({ token, neues_passwort: neuesPasswort }),
  });
}

export function loginMitWiederherstellungscode(preAuthToken: string, wiederherstellungscode: string, rememberDevice = false) {
  return request<TokenResponse>("/auth/login/mfa/wiederherstellungscode", {
    method: "POST",
    headers: bearer(preAuthToken),
    body: JSON.stringify({ wiederherstellungscode, remember_device: rememberDevice }),
  });
}

/** Wie confirmMfaReset in api.ts, liefert aber die einmalig angezeigten Wiederherstellungscodes zurück. */
export function confirmMfaResetMitCodes(accessToken: string, code: string) {
  return request<WiederherstellungscodesAntwort>("/security/mfa/neu-einrichten/bestaetigen", {
    method: "POST",
    headers: bearer(accessToken),
    body: JSON.stringify({ code }),
  });
}

export function wiederherstellungscodesNeu(accessToken: string, aktuellesPasswort: string, aktuellerCode: string) {
  return request<{ wiederherstellungscodes: string[] }>("/security/mfa/wiederherstellungscodes/neu", {
    method: "POST",
    headers: bearer(accessToken),
    body: JSON.stringify({ aktuelles_passwort: aktuellesPasswort, aktueller_code: aktuellerCode }),
  });
}
