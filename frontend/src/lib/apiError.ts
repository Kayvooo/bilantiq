/** FastAPI liefert bei 422 kein detail als String, sondern eine Liste von
 * Pydantic-Fehlern ({loc, msg, ...}). Ohne das hier fiel jede Validierung auf
 * "Etwas ist schiefgelaufen" zurueck — man konnte nie sehen, welches Feld falsch war
 * (siehe Bugreport: POST /kontakte 422 im Log, aber kein Hinweis in der UI). */
export function extractErrorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const meldungen = detail
      .map((eintrag) => {
        if (typeof eintrag !== "object" || eintrag === null) return null;
        const { loc, msg } = eintrag as { loc?: unknown[]; msg?: string };
        const feld = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
        if (typeof msg !== "string") return null;
        return typeof feld === "string" ? `${feld}: ${msg}` : msg;
      })
      .filter((eintrag): eintrag is string => eintrag !== null);
    if (meldungen.length > 0) return meldungen.join("; ");
  }
  return fallback;
}
