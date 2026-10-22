export const MAX_KANTE = 2400;
const JPEG_QUALITAET = 0.85;
const GROESSEN_SCHWELLE = 3 * 1024 * 1024;

export interface Zielgroesse { breite: number; hoehe: number; skaliert: boolean }

export function berechneZielgroesse(breite: number, hoehe: number, maxKante = MAX_KANTE): Zielgroesse {
  const faktor = Math.min(1, maxKante / Math.max(breite, hoehe));
  if (faktor === 1) return { breite, hoehe, skaliert: false };
  return { breite: Math.round(breite * faktor), hoehe: Math.round(hoehe * faktor), skaliert: true };
}

/**
 * Verkleinert grosse Fotos vor dem Upload (laengste Kante 2400 px, JPEG): Handykameras liefern
 * 10 bis 20 MB, fuer die Texterkennung reicht das Zehntel. Die Ausrichtung aus den EXIF-Daten
 * wird dabei angewendet. Kleine Bilder und alles, was nicht gelesen werden kann (PDF, XML,
 * alter Browser), bleiben unveraendert.
 */
export async function verkleinereBild(datei: File): Promise<File> {
  if (!datei.type.startsWith("image/") || typeof createImageBitmap !== "function") return datei;
  try {
    const bild = await createImageBitmap(datei, { imageOrientation: "from-image" });
    const ziel = berechneZielgroesse(bild.width, bild.height);
    if (!ziel.skaliert && datei.size <= GROESSEN_SCHWELLE) {
      bild.close();
      return datei;
    }
    const leinwand = document.createElement("canvas");
    leinwand.width = ziel.breite;
    leinwand.height = ziel.hoehe;
    const kontext = leinwand.getContext("2d");
    if (!kontext) {
      bild.close();
      return datei;
    }
    kontext.fillStyle = "#ffffff"; // PNG-Transparenz wird in JPEG sonst schwarz
    kontext.fillRect(0, 0, ziel.breite, ziel.hoehe);
    kontext.drawImage(bild, 0, 0, ziel.breite, ziel.hoehe);
    bild.close();
    const blob = await new Promise<Blob | null>((fertig) => leinwand.toBlob(fertig, "image/jpeg", JPEG_QUALITAET));
    if (!blob || blob.size >= datei.size) return datei;
    return new File([blob], `${datei.name.replace(/\.[^.]+$/, "")}.jpg`, { type: "image/jpeg" });
  } catch {
    return datei;
  }
}
