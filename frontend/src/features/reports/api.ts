import { ApiError } from "../auth/api";
import { extractErrorDetail } from "../../lib/apiError";
import { notifyUnauthorized } from "../../lib/session";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface Monatswert {
  monat: number;
  einnahmen: string;
  ausgaben: string;
}

export interface OffenePosten {
  anzahl: number;
  betrag: string;
}

export interface NamedBetrag {
  name: string;
  betrag: string;
}

export interface VerlaufEintrag {
  aktion: string;
  kontext: string;
  zeitpunkt: string;
}

export interface Dashboard {
  jahr: number;
  gewinn_vor_steuern: string;
  einnahmen: string;
  ausgaben: string;
  monatswerte: Monatswert[];
  faellige_rechnungen: OffenePosten;
  offene_rechnungen: OffenePosten;
  kleinunternehmergrenze: string;
  umsatz_brutto_jahr: string;
  kassenbestand: string;
  top_kunden: NamedBetrag[];
  top_ausgaben_kategorien: NamedBetrag[];
  verlauf: VerlaufEintrag[];
  hinweis: string;
}

export async function getDashboard(accessToken: string, jahr: number): Promise<Dashboard> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/berichte/dashboard?jahr=${jahr}`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Dashboard;
}

export interface Euer {
  jahr: number;
  zeitraum_von: string;
  zeitraum_bis: string;
  betriebseinnahmen_netto: string;
  anzahl_einnahmen: number;
  betriebsausgaben_netto: string;
  anzahl_ausgaben: number;
  ueberschuss_netto: string;
  offene_forderungen_brutto: string;
  hinweis: string;
}

export async function getEuer(accessToken: string, jahr: number): Promise<Euer> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/berichte/euer?jahr=${jahr}`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Euer;
}

export interface Wochenprognose {
  woche_start: string;
  woche_ende: string;
  erwarteter_zufluss: string;
  anzahl_faellige_rechnungen: number;
  geschaetzter_abfluss: string;
  saldo_veraenderung: string;
  kumulierter_saldo: string;
}

export interface Cashflow {
  heute: string;
  wochen: Wochenprognose[];
  ueberfaellige_rechnungen_betrag: string;
  ueberfaellige_rechnungen_anzahl: number;
  durchschnittliche_wochenausgabe: string;
  warnung: string | null;
  hinweis: string;
}

export async function getCashflow(accessToken: string): Promise<Cashflow> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/berichte/cashflow`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Cashflow;
}

export interface Ustva {
  jahr: number;
  zeitraum_typ: "monat" | "quartal";
  periode: number;
  zeitraum_von: string;
  zeitraum_bis: string;
  umsatz_19_netto: string;
  umsatzsteuer_19: string;
  umsatz_7_netto: string;
  umsatzsteuer_7: string;
  umsatz_sonstige_netto: string;
  umsatzsteuer_gesamt: string;
  vorsteuer_gesamt: string;
  zahllast: string;
  anzahl_rechnungen: number;
  anzahl_ausgaben: number;
  hinweis: string;
}

export async function getUstva(accessToken: string, jahr: number, zeitraumTyp: "monat" | "quartal", periode: number): Promise<Ustva> {
  let response: Response;
  try {
    response = await fetch(
      `${BASE_URL}/berichte/ustva?jahr=${jahr}&zeitraum_typ=${zeitraumTyp}&periode=${periode}`,
      { headers: { Authorization: `Bearer ${accessToken}` } },
    );
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Ustva;
}

export interface SusaKonto {
  konto: string;
  bezeichnung: string;
  soll: string;
  haben: string;
  saldo: string;
}

export interface Susa {
  jahr: number;
  konten: SusaKonto[];
  summe_soll: string;
  summe_haben: string;
  hinweis: string;
}

export async function getSusa(accessToken: string, jahr: number): Promise<Susa> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/berichte/susa?jahr=${jahr}`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Susa;
}

export interface BwaPosten {
  konto: string;
  bezeichnung: string;
  betrag: string;
}

export interface Bwa {
  jahr: number;
  erloes_posten: BwaPosten[];
  kosten_posten: BwaPosten[];
  erloese_gesamt: string;
  kosten_gesamt: string;
  vorlaeufiges_ergebnis: string;
  hinweis: string;
}

export async function getBwa(accessToken: string, jahr: number): Promise<Bwa> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/berichte/bwa?jahr=${jahr}`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, extractErrorDetail(body, "Etwas ist schiefgelaufen."));
  }
  return body as Bwa;
}

export async function downloadDatevExport(accessToken: string, jahr: number): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/berichte/datev-export?jahr=${jahr}`, { headers: { Authorization: `Bearer ${accessToken}` } });
  } catch {
    throw new ApiError(0, "Der Server ist gerade nicht erreichbar.");
  }
  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized();
    throw new ApiError(response.status, "DATEV-Export konnte nicht erstellt werden.");
  }
  return response.blob();
}
