/** Darstellung allein: Beträge bleiben in der API unveränderte Dezimalstrings.
 * BigInt vermeidet Rundungsfehler bei großen Geldbeträgen. Keine Berechnung. */
export function formatMoney(value: string, currency = "EUR"): string {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) return "—";
  const [, sign, integer, fraction = ""] = match;
  const unit = currency === "EUR" ? "€" : currency;
  return `${sign}${BigInt(integer).toLocaleString("de-DE")},${fraction.padEnd(2, "0")}\u00a0${unit}`;
}

export function formatDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  return `${match[3]}.${match[2]}.${match[1]}`;
}

export function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed);
}
