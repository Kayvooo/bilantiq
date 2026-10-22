import { useState } from "react";
import type { KontaktTyp } from "./api";
import type { KontaktFormular } from "./kontaktFormular";

function formatiereIban(iban: string): string {
  return iban.replace(/\s+/g, "").toUpperCase().replace(/(.{4})(?=.)/g, "$1 ");
}

interface Props {
  form: KontaktFormular;
  onChange: (form: KontaktFormular) => void;
  idPrefix: string;
}

export function KontaktFelder({ form, onChange, idPrefix }: Props) {
  const feld = <K extends keyof KontaktFormular>(name: K, wert: KontaktFormular[K]) => onChange({ ...form, [name]: wert });
  const id = (name: string) => `${idPrefix}-${name}`;
  // Abschnitte mit Inhalt starten offen. Nur beim ersten Anzeigen berechnet, damit ein
  // Abschnitt nicht zuklappt, waehrend jemand darin ein Feld leert.
  const [offen] = useState(() => ({
    ansprechpartner: Boolean(form.anrede || form.vorname || form.nachname || form.telefon),
    zahlung: Boolean(form.zahlungsziel_tage || form.skonto_prozent || form.skonto_tage || form.iban || form.bic || form.steuernummer),
    eRechnung: Boolean(form.leitweg_id),
    notiz: Boolean(form.notiz),
  }));

  return (
    <div className="kontakt-felder">
      <div className="field-row">
        <div>
          <label htmlFor={id("typ")}>Art</label>
          <select id={id("typ")} value={form.typ} onChange={(e) => feld("typ", e.target.value as KontaktTyp)}>
            <option value="kunde">Kunde</option>
            <option value="lieferant">Lieferant</option>
            <option value="beide">Kunde und Lieferant</option>
          </select>
        </div>
        <div>
          <label htmlFor={id("name")}>Name oder Firma</label>
          <input id={id("name")} value={form.name} onChange={(e) => feld("name", e.target.value)} required />
        </div>
        <div>
          <label htmlFor={id("email")}>E-Mail</label>
          <input id={id("email")} type="email" value={form.email} onChange={(e) => feld("email", e.target.value)} />
        </div>
      </div>
      <div className="field-row">
        <div>
          <label htmlFor={id("strasse")}>Straße</label>
          <input id={id("strasse")} value={form.strasse} onChange={(e) => feld("strasse", e.target.value)} />
        </div>
        <div>
          <label htmlFor={id("plz")}>PLZ</label>
          <input id={id("plz")} value={form.plz} inputMode="numeric" onChange={(e) => feld("plz", e.target.value)} />
        </div>
        <div>
          <label htmlFor={id("ort")}>Ort</label>
          <input id={id("ort")} value={form.ort} onChange={(e) => feld("ort", e.target.value)} />
        </div>
        <div>
          <label htmlFor={id("land")}>Land</label>
          <input id={id("land")} value={form.land} minLength={2} maxLength={2} required onChange={(e) => feld("land", e.target.value.toUpperCase())} />
        </div>
      </div>
      <div className="field-row">
        <div>
          <label htmlFor={id("ustid")}>USt-IdNr.</label>
          <input id={id("ustid")} value={form.ust_id} onChange={(e) => feld("ust_id", e.target.value)} placeholder="DE123456789" />
        </div>
        <div>
          <label htmlFor={id("kundennummer")}>Kundennummer</label>
          <input id={id("kundennummer")} value={form.kundennummer} onChange={(e) => feld("kundennummer", e.target.value)} placeholder="optional" />
        </div>
      </div>
      <label className="checkbox-row">
        <input type="checkbox" checked={form.ist_geschaeftskunde} onChange={(e) => feld("ist_geschaeftskunde", e.target.checked)} />
        Geschäftskunde (B2B)
      </label>

      <details className="formular-abschnitt" open={offen.ansprechpartner}>
        <summary>Ansprechpartner und Telefon</summary>
        <div className="field-row">
          <div>
            <label htmlFor={id("anrede")}>Anrede</label>
            <input id={id("anrede")} value={form.anrede} list={id("anreden")} onChange={(e) => feld("anrede", e.target.value)} />
            <datalist id={id("anreden")}><option value="Frau" /><option value="Herr" /></datalist>
          </div>
          <div>
            <label htmlFor={id("vorname")}>Vorname</label>
            <input id={id("vorname")} value={form.vorname} onChange={(e) => feld("vorname", e.target.value)} />
          </div>
          <div>
            <label htmlFor={id("nachname")}>Nachname</label>
            <input id={id("nachname")} value={form.nachname} onChange={(e) => feld("nachname", e.target.value)} />
          </div>
          <div>
            <label htmlFor={id("telefon")}>Telefon</label>
            <input id={id("telefon")} type="tel" value={form.telefon} onChange={(e) => feld("telefon", e.target.value)} />
          </div>
        </div>
      </details>

      <details className="formular-abschnitt" open={offen.zahlung}>
        <summary>Zahlung und Bank</summary>
        <div className="field-row">
          <div>
            <label htmlFor={id("zahlungsziel")}>Zahlungsziel (Tage)</label>
            <input id={id("zahlungsziel")} type="number" min={0} max={365} value={form.zahlungsziel_tage} placeholder="Standard" onChange={(e) => feld("zahlungsziel_tage", e.target.value)} />
          </div>
          <div>
            <label htmlFor={id("skonto-prozent")}>Skonto (%)</label>
            <input id={id("skonto-prozent")} inputMode="decimal" value={form.skonto_prozent} placeholder="z. B. 2" onChange={(e) => feld("skonto_prozent", e.target.value)} />
          </div>
          <div>
            <label htmlFor={id("skonto-tage")}>Skonto innerhalb (Tage)</label>
            <input id={id("skonto-tage")} type="number" min={0} max={365} value={form.skonto_tage} onChange={(e) => feld("skonto_tage", e.target.value)} />
          </div>
        </div>
        <div className="field-row">
          <div>
            <label htmlFor={id("iban")}>IBAN</label>
            <input
              id={id("iban")} value={form.iban} autoComplete="off" spellCheck={false}
              onChange={(e) => feld("iban", e.target.value)} onBlur={() => feld("iban", formatiereIban(form.iban))}
            />
          </div>
          <div>
            <label htmlFor={id("bic")}>BIC</label>
            <input id={id("bic")} value={form.bic} autoComplete="off" spellCheck={false} onChange={(e) => feld("bic", e.target.value.toUpperCase())} />
          </div>
          <div>
            <label htmlFor={id("steuernummer")}>Steuernummer</label>
            <input id={id("steuernummer")} value={form.steuernummer} onChange={(e) => feld("steuernummer", e.target.value)} />
          </div>
        </div>
        <p className="auth-hint">Mit hinterlegter IBAN erkennt der Kontoauszug-Abgleich Zahlungen dieses Kontakts leichter.</p>
      </details>

      <details className="formular-abschnitt" open={offen.eRechnung}>
        <summary>E-Rechnung an Behörden</summary>
        <label htmlFor={id("leitweg")}>Leitweg-ID</label>
        <input id={id("leitweg")} value={form.leitweg_id} placeholder="z. B. 04011000-12345-03" onChange={(e) => feld("leitweg_id", e.target.value)} />
        <p className="auth-hint">Öffentliche Auftraggeber nennen dir ihre Leitweg-ID. Sie steht dann in jeder XRechnung an diesen Kontakt.</p>
      </details>

      <details className="formular-abschnitt" open={offen.notiz}>
        <summary>Notiz</summary>
        <textarea id={id("notiz")} aria-label="Notiz" rows={3} value={form.notiz} maxLength={2000} onChange={(e) => feld("notiz", e.target.value)} />
      </details>
    </div>
  );
}
