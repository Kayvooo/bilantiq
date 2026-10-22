type Tone = "ok" | "warn" | "danger" | "neutral";

const TONE_BY_STATUS: Record<string, Tone> = {
  // invoices / quotes
  entwurf: "neutral",
  final: "neutral",
  offen: "neutral",
  versendet: "neutral",
  bezahlt: "ok",
  angenommen: "ok",
  ueberfaellig: "danger",
  abgelaufen: "danger",
  abgelehnt: "danger",
  storniert: "danger",
  // receipts
  neu: "neutral",
  geprueft: "ok",
  unklar: "warn",
  gebucht: "ok",
  aktiv: "ok",
  inaktiv: "neutral",
  vorbereitung: "warn",
  abgeschlossen: "ok",
};

const LABEL_BY_STATUS: Record<string, string> = {
  entwurf: "Entwurf",
  final: "Offen",
  offen: "Offen",
  versendet: "Versendet",
  bezahlt: "Bezahlt",
  angenommen: "Angenommen",
  ueberfaellig: "Überfällig",
  abgelaufen: "Abgelaufen",
  abgelehnt: "Abgelehnt",
  storniert: "Storniert",
  neu: "Neu",
  geprueft: "Geprüft",
  unklar: "Prüfung nötig",
  gebucht: "Gebucht",
  aktiv: "Aktiv",
  inaktiv: "Inaktiv",
  vorbereitung: "Vorbereitung",
  abgeschlossen: "Abgeschlossen",
};

export function StatusPill({ status }: { status: string }) {
  const tone = TONE_BY_STATUS[status] ?? "neutral";
  const label = LABEL_BY_STATUS[status] ?? status;
  return <span className={`status-pill status-pill--${tone}`}>{label}</span>;
}
