/**
 * Frische MFA-Bestaetigung fuer sensible Aktionen (docs/specs/mfa-pflicht.md).
 *
 * Der Server antwortet bei IBAN-Aenderung, Benutzerverwaltung und Gesamtexport ohne gueltige Bestaetigung mit HTTP 428.
 * `mitBestaetigung` fuehrt den Aufruf aus; bei 428 fragt es ueber den Dialog (BestaetigungsDialog) nach einem aktuellen Code,
 * holt das Bestaetigungs-Token und wiederholt den Aufruf genau einmal mit dem Header `X-Bestaetigung`.
 *
 * Das Token wird nur im Arbeitsspeicher gehalten (nie in localStorage), pro Sitzungs-Token und Aktionsklasse, und kuerzer als
 * die serverseitigen fuenf Minuten. Massgeblich bleibt der Server: Lehnt er ein gemerktes Token ab (428), wird neu gefragt.
 */
import { ApiError, type BestaetigungAktion, type ExtraHeaders } from "./api";

export interface BestaetigungsAnfrage {
  accessToken: string;
  aktion: BestaetigungAktion;
  /** Wird mit dem Bestaetigungs-Token (oder null bei "Abbrechen") aufgeloest. */
  fertig: (token: string | null) => void;
}

type Oeffner = (anfrage: BestaetigungsAnfrage) => void;

let oeffner: Oeffner | null = null;

/** Vom Dialog beim Einhaengen gesetzt, beim Entfernen auf null. */
export function setBestaetigungsOeffner(next: Oeffner | null) {
  oeffner = next;
}

function frageNachBestaetigung(accessToken: string, aktion: BestaetigungAktion): Promise<string | null> {
  return new Promise((resolve) => {
    if (!oeffner) {
      resolve(null);
      return;
    }
    oeffner({ accessToken, aktion, fertig: resolve });
  });
}

const MERK_DAUER_MS = 4 * 60 * 1000;
const gemerkt = new Map<string, { token: string; bis: number }>();

function merkSchluessel(accessToken: string, aktion: BestaetigungAktion): string {
  return `${aktion}:${accessToken}`;
}

function gemerktesToken(accessToken: string, aktion: BestaetigungAktion): string | null {
  const eintrag = gemerkt.get(merkSchluessel(accessToken, aktion));
  if (!eintrag) return null;
  if (eintrag.bis <= Date.now()) {
    gemerkt.delete(merkSchluessel(accessToken, aktion));
    return null;
  }
  return eintrag.token;
}

export const BESTAETIGUNG_ABGEBROCHEN = "Die Aktion wurde nicht bestätigt.";

export async function mitBestaetigung<T>(
  accessToken: string,
  aktion: BestaetigungAktion,
  aufruf: (extraHeaders: ExtraHeaders) => Promise<T>,
): Promise<T> {
  const vorhanden = gemerktesToken(accessToken, aktion);
  try {
    return await aufruf(vorhanden ? { "X-Bestaetigung": vorhanden } : {});
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 428) throw err;
    gemerkt.delete(merkSchluessel(accessToken, aktion));
    const token = await frageNachBestaetigung(accessToken, aktion);
    if (token === null) throw new ApiError(428, BESTAETIGUNG_ABGEBROCHEN);
    gemerkt.set(merkSchluessel(accessToken, aktion), { token, bis: Date.now() + MERK_DAUER_MS });
    return aufruf({ "X-Bestaetigung": token });
  }
}
