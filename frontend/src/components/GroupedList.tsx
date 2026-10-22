import type { ReactNode } from "react";
import { ChevronRightIcon } from "./icons";

export function GroupedListSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grouped-list-section">
      <div className="grouped-list-title">{title}</div>
      <div className="grouped-list">{children}</div>
    </div>
  );
}

interface GroupedListRowProps {
  label: string;
  description?: string;
  onClick?: () => void;
  danger?: boolean;
  disabled?: boolean;
}

export function GroupedListRow({ label, description, onClick, danger, disabled }: GroupedListRowProps) {
  return (
    <button type="button" className={`grouped-list-row${danger ? " danger" : ""}`} onClick={onClick} disabled={disabled}>
      <span>{label}{description && <span className="grouped-list-description">{description}</span>}</span>
      {disabled ? <span className="app-sidebar-soon">Bald verfügbar</span> : <ChevronRightIcon width={18} height={18} />}
    </button>
  );
}
