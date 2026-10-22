import type { Kontakt, KontaktEingabe, KontaktTyp } from "./api";

export const LEERES_KONTAKT_FORMULAR = {
  typ: "kunde" as KontaktTyp,
  name: "", strasse: "", plz: "", ort: "", land: "DE", ust_id: "", email: "", ist_geschaeftskunde: true, kundennummer: "",
  anrede: "", vorname: "", nachname: "", telefon: "",
  zahlungsziel_tage: "", skonto_prozent: "", skonto_tage: "", iban: "", bic: "", steuernummer: "",
  leitweg_id: "", notiz: "",
};
export type KontaktFormular = typeof LEERES_KONTAKT_FORMULAR;

const zahlText = (wert: number | string | null | undefined) => (wert === null || wert === undefined ? "" : String(wert));

export function kontaktZuFormular(kontakt: Kontakt): KontaktFormular {
  return {
    typ: kontakt.typ ?? "kunde",
    name: kontakt.name, strasse: kontakt.strasse ?? "", plz: kontakt.plz ?? "", ort: kontakt.ort ?? "",
    land: kontakt.land, ust_id: kontakt.ust_id ?? "", email: kontakt.email ?? "", ist_geschaeftskunde: kontakt.ist_geschaeftskunde,
    kundennummer: kontakt.kundennummer ?? "",
    anrede: kontakt.anrede ?? "", vorname: kontakt.vorname ?? "", nachname: kontakt.nachname ?? "", telefon: kontakt.telefon ?? "",
    zahlungsziel_tage: zahlText(kontakt.zahlungsziel_tage), skonto_prozent: zahlText(kontakt.skonto_prozent),
    skonto_tage: zahlText(kontakt.skonto_tage), iban: kontakt.iban ?? "", bic: kontakt.bic ?? "",
    steuernummer: kontakt.steuernummer ?? "", leitweg_id: kontakt.leitweg_id ?? "", notiz: kontakt.notiz ?? "",
  };
}

const ganzzahl = (wert: string) => (wert.trim() === "" ? null : Number.parseInt(wert, 10));
const text = (wert: string) => wert.trim() || null;

export function formularZuEingabe(form: KontaktFormular): KontaktEingabe {
  return {
    typ: form.typ, name: form.name.trim(), strasse: text(form.strasse), plz: text(form.plz), ort: text(form.ort),
    land: form.land, ust_id: text(form.ust_id), email: text(form.email), ist_geschaeftskunde: form.ist_geschaeftskunde,
    kundennummer: text(form.kundennummer),
    anrede: text(form.anrede), vorname: text(form.vorname), nachname: text(form.nachname), telefon: text(form.telefon),
    zahlungsziel_tage: ganzzahl(form.zahlungsziel_tage),
    skonto_prozent: form.skonto_prozent.trim() ? form.skonto_prozent.trim().replace(",", ".") : null,
    skonto_tage: ganzzahl(form.skonto_tage), iban: text(form.iban), bic: text(form.bic), steuernummer: text(form.steuernummer),
    leitweg_id: text(form.leitweg_id), notiz: text(form.notiz),
  };
}
