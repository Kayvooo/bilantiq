/**
 * Liest den Token des Passwort-Reset-Links aus dem URL-Fragment (`#passwort-zuruecksetzen/<nutzer-id>.<token>`).
 *
 * Warum Fragment statt Query-Parameter: Das Fragment wird vom Browser nie an einen Server gesendet. Der Token landet
 * damit weder im Zugriffslog von Caddy/API noch im Referer-Header ausgehender Anfragen. Ein Query-Parameter
 * (`?token=…`) stünde dagegen im Log jedes Servers und Proxys, der die Seite ausliefert. Der Token wird außerdem sofort
 * aus der Adresszeile entfernt, damit er nicht im Verlauf oder in einem Lesezeichen verbleibt.
 *
 * Das Ergebnis wird im Modul gemerkt: React ruft State-Initialisierer im Entwicklungsmodus doppelt auf, der zweite
 * Aufruf würde das schon entfernte Fragment sonst nicht mehr finden.
 */
const PRAEFIX = "#passwort-zuruecksetzen/";

let gemerkt: string | null | undefined;

export function resetTokenAusUrl(): string | null {
  if (gemerkt !== undefined) return gemerkt;
  const hash = window.location.hash;
  if (hash.startsWith(PRAEFIX)) {
    gemerkt = decodeURIComponent(hash.slice(PRAEFIX.length)).trim() || null;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  } else {
    gemerkt = null;
  }
  return gemerkt;
}

/** Nur für Tests. */
export function resetTokenCacheLeeren() {
  gemerkt = undefined;
}
