import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

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

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const detail = extractErrorDetail(body, "Etwas ist schiefgelaufen.");
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export interface PreAuthResponse {
  /** "mfa_optional": ohne Zwei-Faktor-Anmeldung angemeldet, access_token ist gesetzt.
   * "mfa_einrichtung_erforderlich": MFA ist Pflicht und noch nicht eingerichtet; es gibt nur pre_auth_token (kein access_token). */
  status: "mfa_optional" | "mfa_required" | "mfa_einrichtung_erforderlich";
  pre_auth_token: string;
  access_token?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface MfaSetupResponse {
  secret: string;
  provisioning_uri: string;
}

export interface MeResponse {
  user_id: string;
  mandant_id: string;
  firmenname: string;
  rolle: string;
}

export function register(email: string, password: string, firmenname: string | null, einladungscode: string | null) {
  return request<PreAuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, firmenname, einladungscode }),
  });
}

export function login(email: string, password: string) {
  return request<PreAuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function loginMfa(preAuthToken: string, code: string, rememberDevice = false) {
  return request<TokenResponse>("/auth/login/mfa", {
    method: "POST",
    headers: { Authorization: `Bearer ${preAuthToken}` },
    body: JSON.stringify({ code, remember_device: rememberDevice }),
  });
}

export interface MfaAktiviertAntwort extends TokenResponse {
  /** Nur bei der ersten Aktivierung gesetzt und wird nie wieder angezeigt. */
  wiederherstellungscodes?: string[] | null;
}

/** Pflicht-Einrichtung: Secret holen (mit dem Einrichtungs-Token der Anmeldung, nicht mit einer Sitzung). */
export function mfaSetupMitPreToken(preAuthToken: string) {
  return request<MfaSetupResponse>("/auth/mfa/setup", {
    method: "POST",
    headers: { Authorization: `Bearer ${preAuthToken}` },
  });
}

/** Pflicht-Einrichtung abschliessen: erst jetzt entsteht die volle Sitzung. */
export function mfaVerifyMitPreToken(preAuthToken: string, code: string, rememberDevice = false) {
  return request<MfaAktiviertAntwort>("/auth/mfa/verify", {
    method: "POST",
    headers: { Authorization: `Bearer ${preAuthToken}` },
    body: JSON.stringify({ code, remember_device: rememberDevice }),
  });
}

/** Aktionsklassen, die eine frische MFA-Bestaetigung verlangen (docs/specs/mfa-pflicht.md). */
export type BestaetigungAktion = "iban_aendern" | "benutzer_verwalten" | "gesamtexport";

export interface BestaetigungAntwort {
  bestaetigung_token: string;
  gueltig_bis: string;
}

export function erteileBestaetigung(accessToken: string, aktion: BestaetigungAktion, code: string) {
  return request<BestaetigungAntwort>("/auth/bestaetigung", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ aktion, code }),
  });
}

/** Header fuer eine Aktion mit frischer Bestaetigung (vom Server mit HTTP 428 angefordert). */
export type ExtraHeaders = Record<string, string>;

/** Beendet die aktuelle Sitzung auch serverseitig (der Token wird ungueltig). */
export function logout(accessToken: string) {
  return request<void>("/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function me(accessToken: string) {
  return request<MeResponse>("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}


export interface SecuritySession {
  id: string;
  aktuell: boolean;
  user_agent: string | null;
  erstellt_am: string;
  laeuft_ab_am: string;
}

export interface SecurityOverview {
  email: string;
  mfa_enabled: boolean;
  passwort_geaendert_am: string | null;
  email_geaendert_am: string | null;
  sessions: SecuritySession[];
}

export function getSecurityOverview(accessToken: string) {
  return request<SecurityOverview>("/security", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function startEmailChange(accessToken: string, neuesEmail: string, aktuellesPasswort: string) {
  return request<void>("/security/email/aenderung-starten", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ neues_email: neuesEmail, aktuelles_passwort: aktuellesPasswort }),
  });
}

export function confirmEmailChange(accessToken: string, code: string) {
  return request<void>("/security/email/aenderung-bestaetigen", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ code }),
  });
}

export function revokeOtherSessions(accessToken: string) {
  return request<void>("/security/sessions/andere-abmelden", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function revokeSession(accessToken: string, sessionId: string) {
  return request<void>(`/security/sessions/${sessionId}/abmelden`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function startMfaSetup(accessToken: string) {
  return request<MfaSetupResponse>("/security/mfa/einrichten", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function deactivateMfa(accessToken: string, aktuellesPasswort: string, aktuellerCode: string) {
  return request<void>("/security/mfa/deaktivieren", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ aktuelles_passwort: aktuellesPasswort, aktueller_code: aktuellerCode }),
  });
}

export function startMfaReset(accessToken: string, aktuellesPasswort: string, aktuellerCode: string) {
  return request<MfaSetupResponse>("/security/mfa/neu-einrichten", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ aktuelles_passwort: aktuellesPasswort, aktueller_code: aktuellerCode }),
  });
}

export function confirmMfaReset(accessToken: string, code: string) {
  return request<void>("/security/mfa/neu-einrichten/bestaetigen", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ code }),
  });
}

export function deleteAccount(accessToken: string, passwort: string, mfaCode?: string) {
  return request<void>("/auth/me", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(mfaCode ? { passwort, mfa_code: mfaCode } : { passwort }),
  });
}

export async function fetchDatenexport(accessToken: string, extraHeaders: ExtraHeaders = {}): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/auth/datenexport`, {
    headers: { Authorization: `Bearer ${accessToken}`, ...extraHeaders },
  });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(body, "Datenexport konnte nicht erstellt werden."));
  }
  return response.blob();
}

export type Rechnungsvorlage =
  | "klassisch" | "modern" | "minimal" | "kompakt" | "elegant" | "balken"
  | "seitenleiste" | "rahmen" | "kachel" | "mono" | "stempel";

export type DesignVariante = "standard" | "schwarz" | "blau" | "einfach";
export type LogoGroesse = "S" | "M" | "L";
export type Sprache = "de" | "en";

export interface Mandant {
  id: string;
  firmenname: string;
  ust_id: string | null;
  steuernummer: string | null;
  adresse: string | null;
  datev_beraternummer: string | null;
  datev_mandantennummer: string | null;
  steuerberater_name: string | null;
  steuerberater_email: string | null;
  steuerberater_telefon: string | null;
  rechnungsvorlage: Rechnungsvorlage | null;
  akzentfarbe: string | null;
  fusszeile_text: string | null;
  hat_logo: boolean;
  design_variante: DesignVariante | null;
  logo_groesse: LogoGroesse | null;
  briefpapier_id: string | null;
  sprache: Sprache | null;
  iban: string | null;
  bic: string | null;
  zeige_absenderzeile: boolean;
  zeige_kundennummer: boolean;
  zeige_kontaktperson: boolean;
  zeige_artikelnummer: boolean;
  zeige_positionsbeschreibung: boolean;
  zeige_ust_pro_position: boolean;
  zeige_girocode: boolean;
  zeige_fusszeile: boolean;
  zeige_seitenzahlen: boolean;
  zeige_falz_lochmarken: boolean;
}

export interface MandantUpdate {
  firmenname?: string;
  ust_id?: string;
  steuernummer?: string;
  adresse?: string;
  datev_beraternummer?: string;
  datev_mandantennummer?: string;
  steuerberater_name?: string;
  steuerberater_email?: string;
  steuerberater_telefon?: string;
  rechnungsvorlage?: Rechnungsvorlage;
  akzentfarbe?: string;
  fusszeile_text?: string;
  design_variante?: DesignVariante;
  logo_groesse?: LogoGroesse;
  briefpapier_id?: string | null;
  sprache?: Sprache;
  iban?: string;
  bic?: string;
  zeige_absenderzeile?: boolean;
  zeige_kundennummer?: boolean;
  zeige_kontaktperson?: boolean;
  zeige_artikelnummer?: boolean;
  zeige_positionsbeschreibung?: boolean;
  zeige_ust_pro_position?: boolean;
  zeige_girocode?: boolean;
  zeige_fusszeile?: boolean;
  zeige_seitenzahlen?: boolean;
  zeige_falz_lochmarken?: boolean;
}

export function getMandant(accessToken: string) {
  return request<Mandant>("/auth/mandant", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function updateMandant(accessToken: string, updates: MandantUpdate, extraHeaders: ExtraHeaders = {}) {
  return request<Mandant>("/auth/mandant", {
    method: "PATCH",
    headers: { Authorization: `Bearer ${accessToken}`, ...extraHeaders },
    body: JSON.stringify(updates),
  });
}

export interface Mitglied {
  user_id: string;
  email: string;
  rolle: string;
}

export interface Einladung {
  id: string;
  code: string;
  rolle: string;
  ablauf_am: string;
  eingeloest_am: string | null;
  widerrufen: boolean;
}

export function listMitglieder(accessToken: string) {
  return request<Mitglied[]>("/auth/mitglieder", { headers: { Authorization: `Bearer ${accessToken}` } });
}

export function entferneMitglied(accessToken: string, userId: string, extraHeaders: ExtraHeaders = {}) {
  return request<void>(`/auth/mitglieder/${userId}/entfernen`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, ...extraHeaders },
  });
}

export interface MitgliedDirekt {
  user_id: string;
  email: string;
  rolle: string;
  initial_passwort: string;
}

export function erstelleMitgliedDirekt(accessToken: string, email: string, rolle: "mitglied" | "owner", extraHeaders: ExtraHeaders = {}) {
  return request<MitgliedDirekt>("/auth/mitglieder", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, ...extraHeaders },
    body: JSON.stringify({ email, rolle }),
  });
}

export function passwortAendern(accessToken: string, aktuellesPasswort: string, neuesPasswort: string) {
  return request<void>("/auth/passwort/aendern", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ aktuelles_passwort: aktuellesPasswort, neues_passwort: neuesPasswort }),
  });
}

export function listEinladungen(accessToken: string) {
  return request<Einladung[]>("/auth/einladungen", { headers: { Authorization: `Bearer ${accessToken}` } });
}

export function createEinladung(accessToken: string, rolle: "mitglied" | "owner", extraHeaders: ExtraHeaders = {}) {
  return request<Einladung>("/auth/einladungen", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, ...extraHeaders },
    body: JSON.stringify({ rolle }),
  });
}

export function widerrufeEinladung(accessToken: string, einladungId: string) {
  return request<Einladung>(`/auth/einladungen/${einladungId}/widerrufen`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export async function uploadLogo(accessToken: string, file: File): Promise<Mandant> {
  const form = new FormData();
  form.append("file", file);
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/auth/mandant/logo`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body: form,
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Logo konnte nicht hochgeladen werden."));
  }
  return body as Mandant;
}

export function deleteLogo(accessToken: string) {
  return request<Mandant>("/auth/mandant/logo", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export async function fetchLogoBlob(accessToken: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/auth/mandant/logo`, { headers: { Authorization: `Bearer ${accessToken}` } });
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, "Logo konnte nicht geladen werden.");
  }
  return response.blob();
}

export interface RechnungsvorlageVorschauOptions {
  vorlage?: Rechnungsvorlage;
  akzentfarbe?: string;
  fusszeile_text?: string;
  design_variante?: DesignVariante;
  logo_groesse?: LogoGroesse;
  sprache?: Sprache;
  briefpapier_id?: string | null;
  iban?: string;
  bic?: string;
  zeige_absenderzeile?: boolean;
  zeige_kundennummer?: boolean;
  zeige_kontaktperson?: boolean;
  zeige_artikelnummer?: boolean;
  zeige_positionsbeschreibung?: boolean;
  zeige_ust_pro_position?: boolean;
  zeige_girocode?: boolean;
  zeige_fusszeile?: boolean;
  zeige_seitenzahlen?: boolean;
  zeige_falz_lochmarken?: boolean;
}

/** Vorschau-PDF mit ungespeicherter Auswahl. POST mit JSON-Body statt GET mit Query: IBAN/BIC und Fusszeilentext
 * duerfen nicht in der URL stehen (Server-/Proxy-Logs, Browser-Verlauf). Nur gesetzte Felder werden gesendet;
 * `briefpapier_id: null` heisst "kein Briefpapier", ein fehlendes Feld "gespeicherten Wert behalten".
 * Antwort ist das PDF; als Blob geliefert, damit der Aufrufer eine Blob-URL fuer das iframe bilden kann. */
export async function previewRechnungsvorlage(
  accessToken: string,
  options: RechnungsvorlageVorschauOptions,
): Promise<Blob> {
  const body = Object.fromEntries(Object.entries(options).filter(([, wert]) => wert !== undefined));
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/auth/mandant/rechnungsvorlage/vorschau`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar. Bitte prüfe deine Verbindung.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const fehlerBody = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(fehlerBody, "Vorschau konnte nicht geladen werden."));
  }
  return response.blob();
}

export interface Briefpapier {
  id: string;
  name: string;
}

export function listBriefpapier(accessToken: string) {
  return request<Briefpapier[]>("/auth/briefpapier", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export async function uploadBriefpapier(accessToken: string, name: string, file: File): Promise<Briefpapier> {
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/auth/briefpapier`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body: form,
    });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Briefpapier konnte nicht hochgeladen werden."));
  }
  return body as Briefpapier;
}

export function deleteBriefpapier(accessToken: string, id: string) {
  return request<void>(`/auth/briefpapier/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
