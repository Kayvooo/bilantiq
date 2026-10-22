import type { ReactNode } from "react";

interface Props {
  titel: string;
  children: ReactNode;
}

/** Ehrlicher Grenz-Hinweis zu einer bewusst nicht zertifizierten/geprueften Funktion.
 * Gleiche Optik wie die bestehende Lohn-Grenze (.compliance-boundary), damit solche
 * Hinweise im Produkt einheitlich aussehen. */
export function ComplianceHinweis({ titel, children }: Props) {
  return (
    <div className="compliance-boundary" role="note">
      <strong>{titel}</strong>
      <p>{children}</p>
    </div>
  );
}
