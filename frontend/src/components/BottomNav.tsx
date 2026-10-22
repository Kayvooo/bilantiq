import { TABS, type NavTarget } from "../lib/navTabs";

export type { NavTarget };

interface Props {
  active: NavTarget;
  onNavigate: (target: NavTarget) => void;
}

export function BottomNav({ active, onNavigate }: Props) {
  return (
    <nav className="bottom-nav" aria-label="Hauptnavigation">
      {TABS.map(({ target, label, Icon }) => (
        <button
          key={target}
          type="button"
          className={`bottom-nav-item${active === target ? " active" : ""}`}
          onClick={() => onNavigate(target)}
          aria-current={active === target ? "page" : undefined}
        >
          <span className="nav-icon"><Icon width={22} height={22} /></span>
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
