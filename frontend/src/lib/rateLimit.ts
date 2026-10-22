/**
 * Zentrale Behandlung von HTTP 429 (Ratelimit, Brute-Force-Sperre).
 *
 * Jedes Feature-Modul hat sein eigenes api.ts mit eigenem fetch und baut die Fehlermeldung aus
 * `detail` der Antwort. Damit eine 429 ueberall (Login, MFA, Registrierung, Sicherheitsseite,
 * Einladungscode ...) gleich verstaendlich erscheint, ersetzt `installiereRateLimitHinweis()` einmalig
 * `window.fetch`: Bei 429 bekommt die Antwort ein `detail` mit der Wartezeit aus `Retry-After`
 * (Sekunden oder HTTP-Datum). Ohne Header bleibt der deutsche Text des Servers erhalten, sonst gilt
 * ein allgemeiner Text. Status und Header der Antwort bleiben unveraendert.
 */

const ALLGEMEIN = "Zu viele Versuche. Bitte versuche es später erneut.";

/** Sekunden aus einem Retry-After-Wert (Zahl oder HTTP-Datum), sonst null. */
export function retryAfterSekunden(wert: string | null | undefined, jetzt: number = Date.now()): number | null {
  if (!wert) return null;
  const text = wert.trim();
  if (/^\d+$/.test(text)) return Number(text);
  const zeitpunkt = Date.parse(text);
  if (Number.isNaN(zeitpunkt)) return null;
  return Math.max(0, Math.ceil((zeitpunkt - jetzt) / 1000));
}

function dauerText(sekunden: number): string {
  if (sekunden < 60) return sekunden <= 1 ? "1 Sekunde" : `${sekunden} Sekunden`;
  const minuten = Math.ceil(sekunden / 60);
  if (minuten === 1) return "1 Minute";
  if (minuten <= 120) return `${minuten} Minuten`;
  const stunden = Math.ceil(minuten / 60);
  return `${stunden} Stunden`;
}

/** Meldung fuer eine 429-Antwort. `serverText` ist das `detail` des Servers, falls es ein String war. */
export function rateLimitMeldung(retryAfter: string | null | undefined, serverText?: string | null, jetzt?: number): string {
  const sekunden = retryAfterSekunden(retryAfter, jetzt);
  if (sekunden !== null) return `Zu viele Versuche. Bitte versuche es in ${dauerText(sekunden)} erneut.`;
  return serverText && serverText.trim() ? serverText : ALLGEMEIN;
}

let installiert = false;

export function installiereRateLimitHinweis(ziel: { fetch: typeof fetch } = window) {
  if (installiert) return;
  installiert = true;
  const original = ziel.fetch.bind(ziel);
  ziel.fetch = async (...args: Parameters<typeof fetch>) => {
    const antwort = await original(...args);
    if (antwort.status !== 429) return antwort;
    const body = await antwort.clone().json().catch(() => null) as { detail?: unknown } | null;
    const serverText = typeof body?.detail === "string" ? body.detail : null;
    const neu = new Response(JSON.stringify({ detail: rateLimitMeldung(antwort.headers.get("Retry-After"), serverText) }), {
      status: 429,
      statusText: antwort.statusText,
      headers: { "Content-Type": "application/json", ...(antwort.headers.get("Retry-After") ? { "Retry-After": antwort.headers.get("Retry-After") as string } : {}) },
    });
    return neu;
  };
}

/** Nur fuer Tests: erlaubt erneutes Installieren. */
export function zuruecksetzenFuerTest() {
  installiert = false;
}
