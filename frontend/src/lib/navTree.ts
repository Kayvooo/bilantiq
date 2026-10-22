import {
  BankIcon,
  BoxIcon,
  ChartIcon,
  ContactIcon,
  GearIcon,
  HomeIcon,
  InvoiceIcon,
  PuzzleIcon,
  QuoteIcon,
  ReceiptIcon,
  RocketIcon,
  SwapIcon,
  TaxIcon,
  WalletIcon,
} from "../components/icons";

/** Ziele, die die Desktop-Sidebar direkt anspringen kann — die Teilmenge der
 * AuthFlow-Steps, die von jedem Punkt aus ohne Umweg ueber "Mehr" erreichbar sein soll. */
export type DesktopStep = "home" | "ersteSchritte" | "assistant" | "invoices" | "quotes" | "receipts" | "euer" | "cashflow" | "ustva" | "payroll" | "settings" | "contacts" | "mahnungen" | "susa" | "bwa" | "wiederkehrend" | "gutschriften" | "wiederkehrendAusgaben" | "anlagen" | "bank" | "kassenbuch" | "benutzer" | "security" | "steuerberater" | "auftragsbestaetigung" | "lieferscheine" | "rechnungsvorlage" | "produkte" | "einnahmen" | "buchhaltungseinstellungen" | "umzug";

export interface NavChild {
  label: string;
  step?: DesktopStep;
}

export interface NavItem {
  label: string;
  step?: DesktopStep;
  Icon: typeof HomeIcon;
  children?: NavChild[];
  /** Nur fuer den Inhaber sichtbar (ausgeblendet, sobald feststeht, dass der Nutzer ein Mitglied ist). */
  nurInhaber?: boolean;
}

/* Struktur uebernommen von der sevdesk-Desktop-Navigation (Referenz vom Owner), Labels/Icons
 * bleiben Bilantiq-eigen. Punkte ohne "step" existieren als Feature noch nicht und sind in der
 * UI sichtbar, aber deaktiviert ("Bald verfuegbar") statt einfach zu fehlen. */
export const NAV_TREE: NavItem[] = [
  { label: "Erste Schritte", step: "ersteSchritte", Icon: RocketIcon },
  { label: "Übersicht", step: "home", Icon: HomeIcon },
  { label: "KI-Assistent", step: "assistant", Icon: PuzzleIcon },
  {
    label: "Aufträge", step: "quotes", Icon: QuoteIcon,
    children: [
      { label: "Angebote", step: "quotes" },
      { label: "Auftragsbestätigung", step: "auftragsbestaetigung" },
      { label: "Lieferscheine", step: "lieferscheine" },
    ],
  },
  {
    label: "Rechnungen", step: "invoices", Icon: InvoiceIcon,
    children: [
      { label: "Sonstige Einnahmen", step: "einnahmen" },
      { label: "Wiederkehrend", step: "wiederkehrend" },
      { label: "Mahnungen", step: "mahnungen" },
      { label: "Gutschriften", step: "gutschriften" },
    ],
  },
  {
    label: "Ausgaben", step: "receipts", Icon: ReceiptIcon,
    children: [
      { label: "Wiederkehrend", step: "wiederkehrendAusgaben" },
      { label: "Anlagen", step: "anlagen" },
    ],
  },
  {
    label: "Bank", Icon: BankIcon,
    children: [
      { label: "Kontoauszug", step: "bank" },
      { label: "Kassenbuch", step: "kassenbuch" },
    ],
  },
  {
    label: "Steuern", Icon: TaxIcon,
    children: [
      { label: "UStVA", step: "ustva" },
      { label: "EÜR", step: "euer" },
      { label: "Mein Steuerberater", step: "steuerberater" },
    ],
  },
  {
    label: "Auswertungen", Icon: ChartIcon,
    children: [
      { label: "Cashflow-Prognose", step: "cashflow" },
      { label: "SuSa", step: "susa" },
      { label: "BWA", step: "bwa" },
    ],
  },
  {
    label: "Lohn", Icon: WalletIcon, nurInhaber: true,
    children: [
      { label: "Lohnvorbereitung", step: "payroll" },
    ],
  },
];

export const NAV_TREE_VERWALTEN: NavItem[] = [
  { label: "Kontakte", step: "contacts", Icon: ContactIcon },
  { label: "Produkte", step: "produkte", Icon: BoxIcon },
  { label: "Datenumzug", step: "umzug", Icon: SwapIcon },
  { label: "Erweiterungen", Icon: PuzzleIcon },
  {
    label: "Einstellungen", Icon: GearIcon,
    children: [
      { label: "Benutzer & Rechte", step: "benutzer" },
      { label: "Sicherheit & Datenschutz", step: "security" },
      { label: "Buchhaltung", step: "buchhaltungseinstellungen" },
      { label: "Unternehmen", step: "settings" },
      { label: "System" },
      { label: "Rechnungsdesign", step: "rechnungsvorlage" },
      { label: "Textvorlagen" },
    ],
  },
];
