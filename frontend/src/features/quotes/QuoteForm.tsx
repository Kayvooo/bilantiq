import { useEffect, useState, type FormEvent } from "react";
import { dezimalEingabe } from "../../lib/decimalInput";
import { ApiError } from "../auth/api";
import {
  ustSatzFuerNeuePosition,
  type Buchhaltungseinstellungen,
} from "../buchhaltungseinstellungen/api";
import type { Kontakt } from "../invoices/api";
import type { InvoicePosition } from "../invoices/api";
import { createQuote, type Quote, type QuoteDraft } from "./api";

interface Props {
  accessToken: string;
  kontakte: Kontakt[];
  einstellungen: Buchhaltungseinstellungen;
  onCreated: (quote: Quote) => void;
  onNewKontakt: () => void;
  initialDraft?: QuoteDraft;
}

const LEER_POSITION: InvoicePosition = { beschreibung: "", menge: "1", einzelpreis: "0.00", ust_satz: "19.00" };

function heute(offsetTage = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetTage);
  return d.toISOString().slice(0, 10);
}

export function QuoteForm({ accessToken, kontakte, einstellungen, onCreated, onNewKontakt, initialDraft }: Props) {
  const standardUstSatz = ustSatzFuerNeuePosition(einstellungen);
  const [kontaktId, setKontaktId] = useState(initialDraft?.kontakt_id ?? kontakte[0]?.id ?? "");
  const [gueltigBis, setGueltigBis] = useState(initialDraft?.gueltig_bis ?? heute(einstellungen.standard_zahlungsziel_tage));
  const [positionen, setPositionen] = useState<InvoicePosition[]>(
    initialDraft?.positionen?.length
      ? initialDraft.positionen.map((p) => ({ ...p }))
      : [{ ...LEER_POSITION, ust_satz: standardUstSatz }],
  );
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!initialDraft) return;
    setKontaktId(initialDraft.kontakt_id);
    setGueltigBis(initialDraft.gueltig_bis);
    setPositionen(initialDraft.positionen.map((p) => ({ ...p })));
  }, [initialDraft]);

  function updatePosition(index: number, field: keyof InvoicePosition, value: string) {
    const eingabe = field === "menge" || field === "einzelpreis" || field === "ust_satz" ? dezimalEingabe(value) : value;
    setPositionen((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: eingabe } : p)));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!kontaktId) {
      setStatus("error");
      setError("Bitte zuerst einen Kontakt anlegen oder auswählen.");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const quote = await createQuote(accessToken, { kontakt_id: kontaktId, gueltig_bis: gueltigBis, waehrung: "EUR", positionen });
      onCreated(quote);
      setPositionen([{ ...LEER_POSITION, ust_satz: standardUstSatz }]);
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Angebot konnte nicht erstellt werden.");
    }
  }

  if (kontakte.length === 0) {
    return (
      <div className="panel">
        <h2>Neues Angebot</h2>
        <p className="auth-hint">Noch kein Kontakt vorhanden. Lege zuerst einen an.</p>
        <button type="button" onClick={onNewKontakt}>Kontakt anlegen</button>
      </div>
    );
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <h2>Neues Angebot</h2>

      <label htmlFor="q-kontakt">Kunde</label>
      <select id="q-kontakt" value={kontaktId} onChange={(e) => setKontaktId(e.target.value)}>
        {kontakte.map((k) => (<option key={k.id} value={k.id}>{k.name}</option>))}
      </select>
      <button type="button" className="auth-link" onClick={onNewKontakt}>+ neuer Kontakt</button>

      <label htmlFor="q-gueltig">Gültig bis</label>
      <input id="q-gueltig" type="date" value={gueltigBis} onChange={(e) => setGueltigBis(e.target.value)} required />

      <div className="table-scroll">
      <table className="positions-table">
        <thead><tr><th>Beschreibung</th><th>Menge</th><th>Einzelpreis</th><th>USt %</th></tr></thead>
        <tbody>
          {positionen.map((p, i) => (
            <tr key={i}>
              <td><input aria-label={`Beschreibung, Position ${i + 1}`} value={p.beschreibung} onChange={(e) => updatePosition(i, "beschreibung", e.target.value)} required /></td>
              <td><input aria-label={`Menge, Position ${i + 1}`} inputMode="decimal" value={p.menge} onChange={(e) => updatePosition(i, "menge", e.target.value)} required /></td>
              <td><input aria-label={`Einzelpreis, Position ${i + 1}`} inputMode="decimal" value={p.einzelpreis} onChange={(e) => updatePosition(i, "einzelpreis", e.target.value)} required /></td>
              <td><input aria-label={`Umsatzsteuersatz in Prozent, Position ${i + 1}`} inputMode="decimal" value={p.ust_satz} onChange={(e) => updatePosition(i, "ust_satz", e.target.value)} required /></td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <button type="button" className="auth-link" onClick={() => setPositionen((prev) => [
        ...prev,
        { ...LEER_POSITION, ust_satz: standardUstSatz },
      ])}>+ Position</button>

      {status === "error" && <p className="auth-error" role="alert">{error}</p>}
      <button type="submit" disabled={status === "loading"}>{status === "loading" ? "Wird erstellt …" : "Als Entwurf speichern"}</button>
    </form>
  );
}

