import type { ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  onBack?: () => void;
  action?: ReactNode;
}

export function PageHeader({ title, description, onBack, action }: Props) {
  return (
    <header className="page-header">
      {onBack && <button type="button" className="auth-link back-link" onClick={onBack}>← Zurück</button>}
      <div className="page-header-content">
        <div>
          <h1>{title}</h1>
          {description && <p className="page-description">{description}</p>}
        </div>
        {action}
      </div>
    </header>
  );
}
