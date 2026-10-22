/**
 * Jedes Feature-Modul hat sein eigenes api.ts mit eigenem fetch-Aufruf (siehe
 * AGENTS.md/CLAUDE.md fuer den Kontext) -- ohne diese gemeinsame Stelle wuerde ein
 * abgelaufenes Token auf jeder Seite ausser dem Dashboard zu einer haengenden
 * Fehlermeldung fuehren statt zurueck zum Login zu fuehren.
 */
type UnauthorizedHandler = () => void;

let handler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(next: UnauthorizedHandler | null) {
  handler = next;
}

export function notifyUnauthorized() {
  handler?.();
}
