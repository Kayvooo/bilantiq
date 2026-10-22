import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function anfrage(path: string, accessToken: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers: { Authorization: `Bearer ${accessToken}`, ...init?.headers } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return response;
}

const json = async <T>(path: string, accessToken: string, init?: RequestInit) => (await anfrage(path, accessToken, init)).json() as Promise<T>;
const blob = async (path: string, accessToken: string, init?: RequestInit) => (await anfrage(path, accessToken, init)).blob();

export type StammdatenZiel = "kontakte" | "produkte" | "rechnungen";
/** Export und Vorlage-Export gibt es nur fuer Kontakte und Produkte. */
export type ExportZiel = "kontakte" | "produkte";
export type ExportFormat = "csv" | "xlsx";

export interface FeldInfo {
  schluessel: string;
  label: string;
  pflicht: boolean;
  typ: string;
}

export interface ImportVorschau {
  format: "csv" | "xlsx";
  kodierung: string | null;
  trennzeichen: string | null;
  blatt: string | null;
  blaetter: string[];
  kopfzeilen: string[];
  beispielzeilen: string[][];
  anzahl_zeilen: number;
  vorgeschlagene_zuordnung: Record<string, string>;
  dezimal_vorschlag: "komma" | "punkt";
  felder: FeldInfo[];
}

export interface ImportOptionen {
  zuordnung: Record<string, string>;
  dezimal: "komma" | "punkt";
  doppelte: "ueberspringen" | "ergaenzen";
  fehlerhafte_auslassen: boolean;
  standard_ust_satz?: string;
  /** Nur Rechnungsliste: Zahlungsziel, wenn die Datei keine Faelligkeit hat */
  zahlungsziel_tage?: number;
  /** Nur Rechnungsliste: Kunden, die es noch nicht gibt, als Kontakt anlegen */
  fehlende_kunden_anlegen?: boolean;
  blatt?: string | null;
}

export interface PruefZeile {
  nummer: number;
  status: "neu" | "ergaenzen" | "vorhanden" | "doppelt" | "fehler";
  anzeige: string;
  grund: string | null;
  fehler: string[];
  hinweise: string[];
  ergaenzt: string[];
}

export interface Pruefbericht {
  ziel: StammdatenZiel;
  anzahl_zeilen: number;
  neu: number;
  ergaenzen: number;
  vorhanden: number;
  doppelt: number;
  fehler: number;
  mit_hinweisen: number;
  zeilen: PruefZeile[];
  beispiele: Record<string, string>[];
}

export interface ImportErgebnis extends Pruefbericht {
  import_id: string;
}

export interface ImportProtokoll {
  id: string;
  ziel: StammdatenZiel;
  dateiname: string;
  erstellt_am: string;
  anzahl_neu: number;
  anzahl_ergaenzt: number;
  anzahl_uebersprungen: number;
  anzahl_fehler: number;
  rueckgaengig_am: string | null;
}

function formular(file: File, optionen?: Partial<ImportOptionen>): FormData {
  const form = new FormData();
  form.append("file", file);
  if (optionen) form.append("optionen", JSON.stringify(optionen));
  return form;
}

export const importVorschau = (accessToken: string, ziel: StammdatenZiel, file: File, blatt?: string | null) =>
  json<ImportVorschau>(`/stammdaten/${ziel}/import/vorschau`, accessToken, { method: "POST", body: formular(file, blatt ? { blatt } : undefined) });

export const pruefeImport = (accessToken: string, ziel: StammdatenZiel, file: File, optionen: ImportOptionen) =>
  json<Pruefbericht>(`/stammdaten/${ziel}/import/pruefen`, accessToken, { method: "POST", body: formular(file, optionen) });

export const importiere = (accessToken: string, ziel: StammdatenZiel, file: File, optionen: ImportOptionen) =>
  json<ImportErgebnis>(`/stammdaten/${ziel}/import`, accessToken, { method: "POST", body: formular(file, optionen) });

export const ladeFehlerliste = (accessToken: string, ziel: StammdatenZiel, file: File, optionen: ImportOptionen) =>
  blob(`/stammdaten/${ziel}/import/fehlerliste`, accessToken, { method: "POST", body: formular(file, optionen) });

export const listeImporte = (accessToken: string) => json<ImportProtokoll[]>("/stammdaten/importe", accessToken);

export const macheImportRueckgaengig = (accessToken: string, importId: string) =>
  json<{ geloescht: number; behalten: number }>(`/stammdaten/importe/${importId}/rueckgaengig`, accessToken, { method: "POST" });

export const ladeExport = (accessToken: string, ziel: ExportZiel, format: ExportFormat) =>
  blob(`/stammdaten/${ziel}/export?format=${format}`, accessToken);

export const ladeVorlage = (accessToken: string, ziel: StammdatenZiel, format: ExportFormat) =>
  blob(`/stammdaten/${ziel}/vorlage?format=${format}`, accessToken);
