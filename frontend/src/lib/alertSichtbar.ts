import { useEffect } from "react";

function alarmFuer(knoten: Node | null): HTMLElement | null {
  const element = knoten instanceof HTMLElement ? knoten : knoten?.parentElement ?? null;
  if (!element) return null;
  return element.closest<HTMLElement>('[role="alert"]') ?? element.querySelector<HTMLElement>('[role="alert"]');
}

/** Fehlermeldungen stehen auf vielen Seiten oben, die auslösende Aktion (Speichern, Buchen, Senden) liegt aber oft
 * weiter unten. Sobald ein role="alert" neu erscheint oder seinen Text ändert und außerhalb des sichtbaren Bereichs
 * liegt, wird er in den Blick gescrollt. Screenreader bekommen die Meldung ohnehin über role="alert". */
export function useAlertSichtbar(aktiv: boolean) {
  useEffect(() => {
    if (!aktiv) return;
    const wurzel = document.getElementById("main-content");
    if (!wurzel) return;
    const beobachter = new MutationObserver((aenderungen) => {
      for (const aenderung of aenderungen) {
        const kandidaten = aenderung.type === "childList" ? [...aenderung.addedNodes] : [aenderung.target];
        for (const knoten of kandidaten) {
          const alarm = alarmFuer(knoten);
          if (!alarm) continue;
          const lage = alarm.getBoundingClientRect();
          if (lage.top < 0 || lage.bottom > window.innerHeight) alarm.scrollIntoView({ block: "center" });
          return;
        }
      }
    });
    beobachter.observe(wurzel, { childList: true, subtree: true, characterData: true });
    return () => beobachter.disconnect();
  }, [aktiv]);
}
