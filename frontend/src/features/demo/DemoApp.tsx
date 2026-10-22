import { useState } from "react";
import { Brand } from "../../components/Brand";
import { BottomNav, type NavTarget } from "../../components/BottomNav";
import { GroupedListRow, GroupedListSection } from "../../components/GroupedList";
import { PageHeader } from "../../components/PageHeader";
import { StatusPill } from "../../components/StatusPill";
import { PlusIcon, ScanIcon } from "../../components/icons";
import { formatMoney } from "../../lib/format";

type View = NavTarget | "payroll";

const invoices = [
  { number: "RE-2026-0041", contact: "Studio Nordlicht", date: "05.09.2026", amount: "2499.00", status: "versendet" },
  { number: "RE-2026-0040", contact: "Lena Sommer", date: "28.08.2026", amount: "1249.50", status: "bezahlt" },
  { number: "RE-2026-0039", contact: "Kern & Co.", date: "14.08.2026", amount: "890.00", status: "ueberfaellig" },
];

function PreviewHeader() {
  return <header className="topbar"><Brand /><span className="preview-badge">Mobile Vorschau</span></header>;
}

function Dashboard({ onNavigate }: { onNavigate: (view: View) => void }) {
  return <div className="dashboard-page">
    <div className="dashboard-topbar"><div className="dashboard-avatar">MS</div><div className="dashboard-topbar-text"><div className="name">Musterstudio</div><div className="email">Beispieldaten · September 2026</div></div></div>
    <PageHeader title="Guten Morgen, Mia" description="Dein Unternehmen auf einen Blick." />
    <section className="panel dashboard-summary">
      <p className="dashboard-summary-label">Verfügbarer Überschuss</p><p className="dashboard-summary-value">18.450,00&nbsp;€</p>
      <div className="dashboard-summary-legend"><div className="dashboard-summary-legend-item">Einnahmen<span className="dashboard-summary-legend-value">24.890,00&nbsp;€</span></div><div className="dashboard-summary-legend-item">Ausgaben<span className="dashboard-summary-legend-value">6.440,00&nbsp;€</span></div></div>
    </section>
    <div className="quick-actions"><button type="button" className="button-primary" onClick={() => onNavigate("invoices")}><PlusIcon width={18} /> Rechnung</button><button type="button" onClick={() => onNavigate("receipts")}><ScanIcon width={18} /> Beleg erfassen</button></div>
    <section className="panel"><h2>Offene Forderungen</h2><div className="receivables-value">{formatMoney("3389.00")}</div><p className="auth-hint">2 Rechnungen warten auf Zahlung, davon 1 überfällig.</p></section>
  </div>;
}

function Documents({ kind }: { kind: "invoices" | "quotes" }) {
  const isInvoice = kind === "invoices";
  return <div className="invoices-page"><PageHeader title={isInvoice ? "Rechnungen" : "Angebote"} description={isInvoice ? "Ausgänge, Zahlungen und Fälligkeiten im Blick." : "Angebote erstellen und Status verfolgen."} action={<button type="button" className="button-primary"><PlusIcon width={18} /> Neu</button>} />
    <div className="table-scroll"><table className="positions-table"><thead><tr><th>Nummer</th><th>Kundschaft</th><th>Datum</th><th>Status</th><th className="number">Betrag</th></tr></thead><tbody>{invoices.slice(0, isInvoice ? 3 : 2).map((item, index) => <tr key={item.number}><td>{isInvoice ? item.number : `AN-2026-00${17 - index}`}</td><td>{item.contact}</td><td>{item.date}</td><td><StatusPill status={isInvoice ? item.status : index === 0 ? "versendet" : "angenommen"} /></td><td className="number">{formatMoney(item.amount)}</td></tr>)}</tbody></table></div>
  </div>;
}

function Receipts() {
  return <div className="invoices-page"><PageHeader title="Belege" description="Lokale OCR liest Belege vor. Du bestätigst die Werte." />
    <section className="panel upload-panel"><div className="upload-zone"><ScanIcon width={36} height={36} /><label>Foto, Scan oder PDF auswählen</label><button type="button" className="button-primary">Beleg auswählen</button><p className="auth-hint">Die Verarbeitung läuft lokal ohne kostenpflichtige KI-API.</p></div></section>
    <div className="table-scroll"><table className="positions-table"><thead><tr><th>Anbieter</th><th>Datum</th><th>Kategorie</th><th>Status</th><th className="number">Betrag</th></tr></thead><tbody><tr><td>Deutsche Bahn</td><td>03.09.2026</td><td>Reisekosten</td><td><StatusPill status="geprueft" /></td><td className="number">89,90&nbsp;€</td></tr><tr><td>Bürozentrum West</td><td>01.09.2026</td><td><span className="tag-unklar">[UNKLAR] Bürobedarf</span></td><td><StatusPill status="unklar" /></td><td className="number">47,54&nbsp;€</td></tr></tbody></table></div>
  </div>;
}

function More({ onPayroll }: { onPayroll: () => void }) {
  return <div className="invoices-page"><PageHeader title="Mehr" description="Auswertungen, Lohnvorbereitung und Konto." /><GroupedListSection title="Unternehmen"><GroupedListRow label="Lohnvorbereitung" description="Mitarbeitende und Monatswerte vorbereiten" onClick={onPayroll} /><GroupedListRow label="Kontakte" description="Kundschaft und Lieferanten" onClick={() => undefined} /></GroupedListSection><GroupedListSection title="Auswertungen"><GroupedListRow label="EÜR" description="Einnahmen und Ausgaben" onClick={() => undefined} /><GroupedListRow label="Cashflow" description="Zahlungsströme verstehen" onClick={() => undefined} /><GroupedListRow label="UStVA" description="Umsatzsteuer vorbereiten" onClick={() => undefined} /></GroupedListSection></div>;
}

function Payroll({ onBack }: { onBack: () => void }) {
  return <div className="invoices-page"><PageHeader title="Lohnvorbereitung" description="Mitarbeiterdaten und monatliche Bruttowerte für die Steuerkanzlei vorbereiten." onBack={onBack} />
    <div className="compliance-boundary"><strong>Vorbereitung, keine Lohnabrechnung</strong><p>Gesetzliche Steuern und Sozialabgaben werden noch nicht berechnet. Ein verbindlicher Abschluss oder elektronischer Versand ist bis zur amtlichen Systemprüfung gesperrt.</p></div>
    <div className="section-heading-row"><h2 className="section-title">Mitarbeitende</h2><button type="button" className="button-primary"><PlusIcon width={18} /> Person anlegen</button></div>
    <div className="table-scroll"><table className="positions-table"><thead><tr><th>Personalnummer</th><th>Name</th><th>Monatsbrutto</th><th>Status</th></tr></thead><tbody><tr><td>MA-001</td><td>Lea Becker</td><td className="number">3.300,00&nbsp;€</td><td><StatusPill status="aktiv" /></td></tr><tr><td>MA-002</td><td>Jonas Richter</td><td className="number">2.850,00&nbsp;€</td><td><StatusPill status="aktiv" /></td></tr></tbody></table></div>
    <h2 className="section-title">September 2026 vorbereiten</h2><section className="panel"><h2>Monatsentwurf</h2><div className="euer-row"><span>Gesamtbrutto · 2 Personen</span><strong>6.150,00&nbsp;€</strong></div><div className="euer-row"><span>Status</span><StatusPill status="vorbereitung" /></div><button type="button" className="button-primary">CSV-Arbeitsdatei</button></section>
  </div>;
}

export function DemoApp() {
  const [view, setView] = useState<View>("home");
  const nav = view === "payroll" ? "more" : view;
  return <><a className="skip-link" href="#main">Zum Inhalt</a><PreviewHeader /><main id="main" className="app-shell">
    {view === "home" && <Dashboard onNavigate={setView} />}{view === "invoices" && <Documents kind="invoices" />}{view === "quotes" && <Documents kind="quotes" />}{view === "receipts" && <Receipts />}{view === "more" && <More onPayroll={() => setView("payroll")} />}{view === "payroll" && <Payroll onBack={() => setView("more")} />}
  </main><BottomNav active={nav} onNavigate={setView} /></>;
}
