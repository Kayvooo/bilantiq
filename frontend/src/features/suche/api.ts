import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface SucheTreffer {
  id: string;
  titel: string;
  untertitel: string | null;
  /** Name der Zielseite (DesktopStep) */
  ziel: string;
}

export interface SucheGruppe {
  typ: string;
  label: string;
  treffer: SucheTreffer[];
  /** alle Treffer dieses Typs, nicht nur die gezeigten */
  gesamt: number;
}

export interface SucheErgebnis {
  gruppen: SucheGruppe[];
  /** Typen, bei denen die Obergrenze erreicht wurde und nicht alles durchsucht ist */
  unvollstaendig: string[];
}

/** POST statt GET: Suchbegriffe (Kundennamen, Betraege) sollen nicht in Server- und Proxy-Logs landen. */
export async function sucheAnfrage(accessToken: string, q: string, signal?: AbortSignal): Promise<SucheErgebnis> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/suche`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ q }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorDetail(body, "Die Suche ist fehlgeschlagen."));
  }
  return response.json() as Promise<SucheErgebnis>;
}
