import { useState } from "react";
import { paletteKuerzel } from "../lib/paletteKuerzel";
import { ChevronRightIcon, SearchIcon } from "./icons";
import type { Step } from "../features/auth/AuthFlow";
import { NAV_TREE, NAV_TREE_VERWALTEN, type DesktopStep, type NavItem } from "../lib/navTree";

interface Props {
  active: Step["name"];
  onNavigate: (step: DesktopStep) => void;
  onSuche: () => void;
  onLogout: () => void;
  /** true, sobald feststeht, dass der Nutzer nur Mitglied ist: Inhaber-Bereiche (Lohn) werden ausgeblendet. */
  istMitglied?: boolean;
}

function isGroupActive(item: NavItem, active: string): boolean {
  return item.step === active || (item.children?.some((child) => child.step === active) ?? false);
}

function NavGroup({ item, active, onNavigate }: { item: NavItem; active: string; onNavigate: (step: DesktopStep) => void }) {
  const [manuallyOpen, setManuallyOpen] = useState(false);
  const open = isGroupActive(item, active) || manuallyOpen;
  // Zeigt ein Unterpunkt dieselbe Seite (z. B. Aufträge > Angebote), leuchtet nur der Unterpunkt.
  const headerActive = item.step === active && !item.children?.some((child) => child.step === active);
  const canExpand = !item.step && !!item.children;

  function handleHeaderClick() {
    if (item.step) onNavigate(item.step);
    else if (item.children) setManuallyOpen((prev) => !prev);
  }

  return (
    <div className="app-sidebar-group">
      <button
        type="button"
        className={`app-sidebar-item${headerActive ? " active" : ""}${open && !headerActive ? " expanded" : ""}`}
        disabled={!item.step && !item.children}
        onClick={handleHeaderClick}
        aria-current={headerActive ? "page" : undefined}
        aria-expanded={item.children ? open : undefined}
      >
        <span className="nav-icon"><item.Icon width={20} height={20} /></span>
        <span className="app-sidebar-label">{item.label}</span>
        {canExpand && <ChevronRightIcon className={`app-sidebar-chevron${open ? " open" : ""}`} width={16} height={16} />}
      </button>
      {open && item.children && (
        <div className="app-sidebar-children">
          {item.children.map((child) => (
            <button
              key={child.label}
              type="button"
              className={`app-sidebar-item app-sidebar-child${child.step === active ? " active" : ""}`}
              disabled={!child.step}
              onClick={() => child.step && onNavigate(child.step)}
              aria-current={child.step === active ? "page" : undefined}
            >
              <span>{child.label}</span>
              {!child.step && <span className="app-sidebar-soon">Bald verfügbar</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Desktop-Gegenstück zu BottomNav — nach der vom Owner referenzierten sevdesk-Struktur
 * aufgebaut (Gruppen, nur die aktive/manuell geoeffnete Gruppe zeigt ihre Unterpunkte),
 * Farben/Radien bleiben Bilantiq-eigene Tokens. Sichtbarkeit ist reines CSS
 * (index.css, min-width: 1024px). */
export function Sidebar({ active, onNavigate, onSuche, onLogout, istMitglied = false }: Props) {
  return (
    <nav className="app-sidebar" aria-label="Hauptnavigation">
      <div className="app-sidebar-brand">
        <img className="app-sidebar-logo" src="/brand/logo.svg" alt="Bilantiq" width="150" height="33" />
      </div>
      <div className="app-sidebar-suchzeile">
        <button type="button" className="app-sidebar-suche" onClick={onSuche} aria-label={`Suche und Schnellaktionen öffnen (${paletteKuerzel()})`}>
          <SearchIcon width={18} height={18} aria-hidden="true" />
          <span className="app-sidebar-suche-text">Suchen …</span>
          <kbd>{paletteKuerzel()}</kbd>
        </button>
      </div>
      <div className="app-sidebar-scroll">
        {NAV_TREE.filter((item) => !(item.nurInhaber && istMitglied)).map((item) => (
          <NavGroup key={item.label} item={item} active={active} onNavigate={onNavigate} />
        ))}
        <div className="app-sidebar-section-title">Verwalten</div>
        {NAV_TREE_VERWALTEN.map((item) => (
          <NavGroup key={item.label} item={item} active={active} onNavigate={onNavigate} />
        ))}
      </div>
      <div className="app-sidebar-footer">
        <button type="button" className="app-sidebar-item app-sidebar-logout" onClick={onLogout}>
          <span className="app-sidebar-label">Abmelden</span>
        </button>
        <span>Zahlen klar. Kopf frei.</span>
      </div>
    </nav>
  );
}
