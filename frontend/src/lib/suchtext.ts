/** Kleinschreibung ohne Akzente, ss statt scharfem s: gleiche Regeln wie die Suche im Backend
 * (app/suche/service.py), damit "Müller" ueberall "muller" und "mueller"-aehnliche Eingaben
 * gleich behandelt. */
export function normalisiere(text: string): string {
  return text.toLocaleLowerCase("de").replace(/ß/g, "ss").normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

/** Jedes Wort der Eingabe muss irgendwo im Text vorkommen (UND). Leere Eingabe passt immer. */
export function passtZurSuche(text: string, suche: string): boolean {
  const woerter = normalisiere(suche).split(/\s+/).filter(Boolean);
  if (woerter.length === 0) return true;
  const heuhaufen = normalisiere(text);
  return woerter.every((wort) => heuhaufen.includes(wort));
}

/** Betrag in den Schreibweisen, die jemand eintippen wuerde: 1.240,00 / 1240,00 / 1240.00. */
export function betragSuchtext(wert: string | number | null | undefined): string {
  if (wert === null || wert === undefined || wert === "") return "";
  const zahl = Number(wert);
  if (!Number.isFinite(zahl)) return "";
  const fest = zahl.toFixed(2);
  return `${zahl.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${fest.replace(".", ",")} ${fest}`;
}
