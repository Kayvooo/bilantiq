/** Mobile deutsche Tastaturen liefern ein Komma; die API erwartet Dezimalstrings mit Punkt.
 * Nur den Separator übertragen: keine Rundung, Number-Konvertierung oder Tausender-Erkennung. */
export function dezimalEingabe(value: string): string {
  return value.replace(",", ".");
}
