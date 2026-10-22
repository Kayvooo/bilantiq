import { formatMoney } from "../lib/format";

interface Posten {
  name: string;
  wert: number;
}

interface Props {
  daten: Posten[];
  leerHinweis: string;
}

// Waldgrün führt, Blau vergleicht; weitere Kategorien nutzen neutrale Brand-Tokens.
// Die vorhandene Legende benennt jeden Posten und seinen Betrag zusätzlich zur Farbe.
const FARBEN = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
const RADIUS = 34;
const STRICHBREITE = 14;
const UMFANG = 2 * Math.PI * RADIUS;

export function DonutChart({ daten, leerHinweis }: Props) {
  const gesamt = daten.reduce((sum, d) => sum + d.wert, 0);

  if (daten.length === 0 || gesamt <= 0) {
    return <p className="auth-hint" style={{ margin: 0 }}>{leerHinweis}</p>;
  }

  // Das Loch hat nur ~54 Einheiten Durchmesser: Betragstext bei langen Summen verkleinern, statt in den Ring zu laufen.
  const summeText = formatMoney(gesamt.toFixed(2));
  const summeSchrift = Math.min(11, 50 / (summeText.length * 0.62));

  const laengen = daten.map((d) => (d.wert / gesamt) * UMFANG);
  const segmente = daten.map((d, i) => ({
    ...d,
    laenge: laengen[i],
    dashoffset: -laengen.slice(0, i).reduce((sum, l) => sum + l, 0),
    farbe: FARBEN[i % FARBEN.length],
  }));

  return (
    <div className="donut-chart">
      <svg viewBox="0 0 100 100" className="donut-chart-svg" role="img" aria-label="Verteilung">
        <circle cx="50" cy="50" r={RADIUS} className="donut-chart-basis" />
        {segmente.map((s) => (
          <circle
            key={s.name}
            cx="50" cy="50" r={RADIUS}
            fill="none" stroke={s.farbe} strokeWidth={STRICHBREITE}
            strokeDasharray={`${s.laenge} ${UMFANG - s.laenge}`}
            strokeDashoffset={s.dashoffset}
            transform="rotate(-90 50 50)"
          />
        ))}
        <text x="50" y="47" textAnchor="middle" className="donut-chart-summe" style={{ fontSize: summeSchrift }}>{summeText}</text>
        <text x="50" y="60" textAnchor="middle" className="donut-chart-summe-label">Gesamt</text>
      </svg>
      <ul className="donut-chart-legende">
        {segmente.map((s) => (
          <li key={s.name}>
            <span className="donut-chart-punkt" style={{ background: s.farbe }} />
            <span className="donut-chart-name">{s.name}</span>
            <span className="donut-chart-wert">{formatMoney(s.wert.toFixed(2))}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
