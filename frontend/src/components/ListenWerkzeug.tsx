import type { ListenSteuerung } from "../lib/useListenFilter";

interface Props {
  steuerung: ListenSteuerung;
  placeholder: string;
  ariaLabel: string;
}

/** Kopfzeile ueber einer Liste: Filter-Reiter, Suchfeld und Sortierung. Arbeitet auf den schon
 * geladenen Daten (siehe useListenFilter), fragt also nicht den Server. */
export function ListenWerkzeug({ steuerung, placeholder, ariaLabel }: Props) {
  const { suche, setSuche, filterReiter, filterId, setFilterId, sortOptionen, sortId, setSortId } = steuerung;
  return (
    <div className="liste-kopf">
      {filterReiter.length > 1 && (
        <div className="pill-row" role="group" aria-label="Filtern">
          {filterReiter.map((reiter) => (
            <button
              key={reiter.id} type="button" aria-pressed={filterId === reiter.id}
              className={`pill${filterId === reiter.id ? " pill--aktiv" : ""}`}
              onClick={() => setFilterId(reiter.id)}
            >
              {reiter.label} <span className="pill-anzahl">{reiter.anzahl}</span>
            </button>
          ))}
        </div>
      )}
      <div className="liste-suche-gruppe">
        <input type="search" className="liste-suche" placeholder={placeholder} aria-label={ariaLabel} value={suche} onChange={(e) => setSuche(e.target.value)} />
        {sortOptionen.length > 1 && (
          <select className="liste-sortierung" aria-label="Sortieren nach" value={sortId} onChange={(e) => setSortId(e.target.value)}>
            {sortOptionen.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        )}
      </div>
    </div>
  );
}

/** Hinweis, wenn Suche oder Filter nichts uebrig lassen, obwohl es Eintraege gibt. */
export function KeineListenTreffer({ onZuruecksetzen }: { onZuruecksetzen: () => void }) {
  return (
    <div className="empty-state">
      <h2>Keine Treffer</h2>
      <p className="auth-hint" style={{ margin: 0 }}>Zu Suche und Filter passt kein Eintrag.</p>
      <div className="actions">
        <button type="button" className="auth-link" onClick={onZuruecksetzen}>Suche und Filter zurücksetzen</button>
      </div>
    </div>
  );
}
