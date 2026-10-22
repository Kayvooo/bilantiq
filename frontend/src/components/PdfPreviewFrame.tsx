import { PageState } from "./PageState";

const ZOOM_STUFEN = [50, 75, 100] as const;
export type ZoomStufe = (typeof ZOOM_STUFEN)[number];

const A4_VERHAELTNIS = 1.4142; // ISO 216
const BASISBREITE = 480; // px bei 100 %

function naechsteStufe(aktuell: ZoomStufe, richtung: 1 | -1): ZoomStufe {
  const index = ZOOM_STUFEN.indexOf(aktuell);
  const naechsterIndex = Math.min(ZOOM_STUFEN.length - 1, Math.max(0, index + richtung));
  return ZOOM_STUFEN[naechsterIndex];
}

interface Props {
  title: string;
  url: string | null;
  loading?: boolean;
  fehler?: boolean;
  leerHinweis?: string;
  zoom: ZoomStufe;
  onZoomChange: (zoom: ZoomStufe) => void;
}

export function PdfPreviewFrame({ title, url, loading, fehler, leerHinweis, zoom, onZoomChange }: Props) {
  const breite = BASISBREITE * (zoom / 100);
  const hoehe = breite * A4_VERHAELTNIS;

  return (
    <div className="pdf-vorschau">
      <div className="pdf-vorschau-zoom" role="group" aria-label="Vorschau-Zoom">
        <button
          type="button"
          className="zoom-btn"
          aria-label="Verkleinern"
          onClick={() => onZoomChange(naechsteStufe(zoom, -1))}
          disabled={zoom === ZOOM_STUFEN[0]}
        >
          −
        </button>
        <span className="zoom-wert">{zoom}%</span>
        <button
          type="button"
          className="zoom-btn"
          aria-label="Vergrößern"
          onClick={() => onZoomChange(naechsteStufe(zoom, 1))}
          disabled={zoom === ZOOM_STUFEN[ZOOM_STUFEN.length - 1]}
        >
          +
        </button>
      </div>
      <div className="pdf-vorschau-buehne" role="region" aria-label={`${title}, bei Bedarf seitlich scrollbar`} tabIndex={0}>
        <div className="pdf-vorschau-rahmen" style={{ width: breite, height: hoehe }}>
          {url && <iframe title={title} src={url} className="pdf-vorschau-frame" />}
          {!url && loading && <PageState label="Vorschau wird erzeugt …" />}
          {!url && !loading && !fehler && leerHinweis && <p className="auth-hint pdf-vorschau-leer">{leerHinweis}</p>}
        </div>
      </div>
      {url && loading && <p className="auth-hint pdf-vorschau-status">Vorschau wird aktualisiert …</p>}
      {fehler && <p className="auth-error" role="alert">Vorschau konnte nicht geladen werden.</p>}
    </div>
  );
}
