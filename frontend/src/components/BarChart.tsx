interface Reihe {
  label: string;
  a: number;
  b: number;
}

interface Props {
  daten: Reihe[];
  labelA: string;
  labelB: string;
}

const HOEHE = 188;
const OBEN = 8; // Platz, damit das oberste Achsenlabel nicht am Rand abgeschnitten wird
const BREITE = 640;
const LINKS = 56;
const UNTEN = 24;

export function BarChart({ daten, labelA, labelB }: Props) {
  const maxWert = Math.max(1, ...daten.map((d) => Math.max(d.a, d.b)));
  const stufen = 4;
  const stufenwerte = Array.from({ length: stufen + 1 }, (_, i) => (maxWert / stufen) * i);
  const plotHoehe = HOEHE - UNTEN - OBEN;
  const plotBreite = BREITE - LINKS;
  const gruppenBreite = plotBreite / daten.length;
  const balkenBreite = Math.min(18, gruppenBreite / 3.2);

  function y(wert: number): number {
    return OBEN + plotHoehe - (wert / maxWert) * plotHoehe;
  }

  // Kleine Maximalwerte duerfen auf der Y-Achse nicht durch Rundung
  // zu identischen Labels kollabieren.
  const nachkommastellen = maxWert < stufen ? 2 : 0;

  return (
    <div className="chart-scroll" role="region" aria-label={`${labelA} und ${labelB} je Monat, Diagramm`} tabIndex={0}>
    <svg viewBox={`0 0 ${BREITE} ${HOEHE}`} className="bar-chart" role="img" aria-label={`${labelA} und ${labelB} je Monat`}>
      {stufenwerte.map((wert) => (
        <g key={wert}>
          <line x1={LINKS} x2={BREITE} y1={y(wert)} y2={y(wert)} className="bar-chart-gitter" />
          <text x={LINKS - 8} y={y(wert)} textAnchor="end" dominantBaseline="middle" className="bar-chart-achse">
            {wert.toLocaleString("de-DE", { minimumFractionDigits: nachkommastellen, maximumFractionDigits: nachkommastellen })}
          </text>
        </g>
      ))}
      {daten.map((d, i) => {
        const mitte = LINKS + gruppenBreite * i + gruppenBreite / 2;
        return (
          <g key={d.label}>
            <rect x={mitte - balkenBreite - 2} y={y(d.a)} width={balkenBreite} height={OBEN + plotHoehe - y(d.a)} rx={2} className="bar-chart-a" />
            <rect x={mitte + 2} y={y(d.b)} width={balkenBreite} height={OBEN + plotHoehe - y(d.b)} rx={2} className="bar-chart-b" />
            <text x={mitte} y={HOEHE - 4} textAnchor="middle" className="bar-chart-achse">{d.label}</text>
          </g>
        );
      })}
    </svg>
    </div>
  );
}
