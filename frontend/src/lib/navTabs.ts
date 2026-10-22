import { HomeIcon, InvoiceIcon, MoreIcon, QuoteIcon, ReceiptIcon } from "../components/icons";

export type NavTarget = "home" | "invoices" | "receipts" | "quotes" | "more";

export const TABS: { target: NavTarget; label: string; Icon: typeof HomeIcon }[] = [
  { target: "home", label: "Home", Icon: HomeIcon },
  { target: "invoices", label: "Rechnungen", Icon: InvoiceIcon },
  { target: "receipts", label: "Belege", Icon: ReceiptIcon },
  { target: "quotes", label: "Angebote", Icon: QuoteIcon },
  { target: "more", label: "Mehr", Icon: MoreIcon },
];
