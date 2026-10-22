export function PageState({ label, error, onRetry }: { label: string; error?: boolean; onRetry?: () => void }) {
  return (
    <div className="page-state panel">
      <p className={error ? "auth-error" : "auth-hint"} role={error ? "alert" : "status"}>{label}</p>
      {error && onRetry && <button type="button" className="button-secondary" onClick={onRetry}>Erneut versuchen</button>}
    </div>
  );
}
