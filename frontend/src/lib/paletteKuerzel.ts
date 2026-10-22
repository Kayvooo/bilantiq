import { useEffect } from "react";

/** Beschriftung des Tastenkuerzels, je nach Plattform. */
export function paletteKuerzel(): string {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/i.test(navigator.userAgent) ? "⌘ K" : "Strg K";
}

/** Strg+K bzw. Cmd+K oeffnet und schliesst die Palette. */
export function usePaletteKuerzel(aktiv: boolean, umschalten: () => void) {
  useEffect(() => {
    if (!aktiv) return;
    function bei(ereignis: KeyboardEvent) {
      // Liegt ein anderer modaler Dialog (z. B. der MFA-Hinweis) oben, darf die Palette nicht darueber aufgehen.
      if (document.querySelector("[role=dialog][aria-modal=true]:not(.palette)")) return;
      if ((ereignis.ctrlKey || ereignis.metaKey) && !ereignis.altKey && !ereignis.shiftKey && ereignis.key.toLowerCase() === "k") {
        ereignis.preventDefault();
        umschalten();
      }
    }
    window.addEventListener("keydown", bei);
    return () => window.removeEventListener("keydown", bei);
  }, [aktiv, umschalten]);
}
