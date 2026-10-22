import { useEffect, useRef } from "react";

/** Springt nach der Suche zum gefundenen Datensatz: scrollt die Zeile mit `data-fokus-id` in die
 * Mitte und markiert sie kurz. `bereit` ist true, sobald die Liste geladen ist und den Datensatz
 * enthaelt. Passiert pro `fokusId` genau einmal, damit spaetere Neuladungen nicht erneut springen. */
export function useFokus(fokusId: string | undefined, bereit: boolean) {
  const erledigt = useRef<string | null>(null);
  useEffect(() => {
    if (!fokusId || !bereit || erledigt.current === fokusId) return;
    // kurz warten, damit z. B. ein gerade geoeffnetes Bearbeitungsformular schon im DOM steht
    const timer = window.setTimeout(() => {
      const zeile = document.querySelector<HTMLElement>(`[data-fokus-id="${CSS.escape(fokusId)}"]`);
      if (!zeile) return;
      erledigt.current = fokusId;
      zeile.scrollIntoView({ block: "center" });
      zeile.classList.add("fokus-markiert");
      window.setTimeout(() => zeile.classList.remove("fokus-markiert"), 3000);
    }, 60);
    return () => window.clearTimeout(timer);
  }, [fokusId, bereit]);
}
