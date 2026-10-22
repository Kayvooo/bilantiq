/** Einladungscodes haben 12 Zeichen (Ziffern und Buchstaben, vorher 8). Leerzeichen und Bindestriche aus dem
 * Einfuegen werden entfernt, Gross-/Kleinschreibung ist egal. */
export const EINLADUNGSCODE_LAENGE = 12;

export function normalisiereEinladungscode(eingabe: string): string {
  return eingabe.replace(/[\s-]/g, "").toUpperCase().slice(0, EINLADUNGSCODE_LAENGE);
}

/** Obergrenze fuers Eingabefeld: groesser als der Code, weil der Browser ein eingefuegtes "3F9A-1C7D-02BE" schon
 * vor der Normalisierung auf maxLength kuerzen wuerde und dann Zeichen fehlten. */
export const EINLADUNGSCODE_EINGABE_MAX = EINLADUNGSCODE_LAENGE * 2;
