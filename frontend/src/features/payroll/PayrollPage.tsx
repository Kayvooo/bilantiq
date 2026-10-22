import { Fragment, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { StatusPill } from "../../components/StatusPill";
import { formatDate, formatMoney } from "../../lib/format";
import { ApiError } from "../auth/api";
import { useRollenStatus } from "../../lib/useIstInhaber";
import { downloadBlob } from "../invoices/downloadBlob";
import {
  abschliessenMonatsentwurf,
  createMitarbeiter,
  createMonatsentwurf,
  deactivateMitarbeiter,
  downloadLohnzettel,
  downloadMonthExport,
  listMitarbeitende,
  listMonatsentwuerfe,
  reactivateMitarbeiter,
  reaktivierenMonatsentwurf,
  updateMitarbeiter,
  updateMonatsentwurf,
  type Mitarbeiter,
  type MonatsentwurfUpdate,
  type Monatsentwurf,
} from "./api";

interface Props { accessToken: string; onBack: () => void }

const now = new Date();
const EMPTY_EMPLOYEE = { personalnummer: "", vorname: "", nachname: "", eintrittsdatum: now.toISOString().slice(0, 10), austrittsdatum: "", monatsbrutto: "" };
type EmployeeForm = typeof EMPTY_EMPLOYEE;

function employeeToForm(item: Mitarbeiter): EmployeeForm {
  return {
    personalnummer: item.personalnummer,
    vorname: item.vorname,
    nachname: item.nachname,
    eintrittsdatum: item.eintrittsdatum,
    austrittsdatum: item.austrittsdatum ?? "",
    monatsbrutto: item.monatsbrutto,
  };
}

type EntwurfAmounts = { grundbrutto: string; steuerpflichtige_zuschlaege: string; steuerfreie_erstattungen: string; sonstige_abzuege: string };

function entwurfToForm(item: Monatsentwurf): EntwurfAmounts {
  return {
    grundbrutto: item.grundbrutto,
    steuerpflichtige_zuschlaege: item.steuerpflichtige_zuschlaege,
    steuerfreie_erstattungen: item.steuerfreie_erstattungen,
    sonstige_abzuege: item.sonstige_abzuege,
  };
}

/** Die Lohndaten (Gehaelter, Namen) liefert das Backend nur an den Inhaber. Mitglieder bekommen eine
 * Erklaerung, statt dass die Seite mit einem rohen 403 scheitert. */
export function PayrollPage({ accessToken, onBack }: Props) {
  const rolle = useRollenStatus(accessToken);
  if (rolle === "laedt") return <PageState label="Lohnvorbereitung wird geladen …" />;
  if (rolle === "mitglied") {
    return (
      <div className="invoices-page">
        <PageHeader title="Lohnvorbereitung" description="Mitarbeitende und Monatswerte für die Steuerkanzlei." onBack={onBack} />
        <div className="panel" role="status">
          <h2>Nur für den Inhaber des Kontos</h2>
          <p>Die Lohnvorbereitung enthält Namen und Gehälter der Mitarbeitenden. Deshalb darf nur der Inhaber (Owner) des Kontos sie sehen und bearbeiten.</p>
          <p className="auth-hint">Wende dich an den Inhaber, wenn du Lohndaten brauchst.</p>
        </div>
      </div>
    );
  }
  return <PayrollInhaberSeite accessToken={accessToken} onBack={onBack} />;
}

function PayrollInhaberSeite({ accessToken, onBack }: Props) {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [employees, setEmployees] = useState<Mitarbeiter[]>([]);
  const [drafts, setDrafts] = useState<Monatsentwurf[]>([]);
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [employeeForm, setEmployeeForm] = useState(EMPTY_EMPLOYEE);
  const [selectedEmployee, setSelectedEmployee] = useState("");
  const [amounts, setAmounts] = useState({ grundbrutto: "", steuerpflichtige_zuschlaege: "0.00", steuerfreie_erstattungen: "0.00", sonstige_abzuege: "0.00" });
  const [busy, setBusy] = useState(false);
  const [editEmployeeId, setEditEmployeeId] = useState<string | null>(null);
  const [editEmployeeForm, setEditEmployeeForm] = useState<EmployeeForm>(EMPTY_EMPLOYEE);
  const [editDraftId, setEditDraftId] = useState<string | null>(null);
  const [editDraftForm, setEditDraftForm] = useState<EntwurfAmounts>({ grundbrutto: "0.00", steuerpflichtige_zuschlaege: "0.00", steuerfreie_erstattungen: "0.00", sonstige_abzuege: "0.00" });

  async function reload() {
    setError("");
    try {
      const [employeeResult, draftResult] = await Promise.all([
        listMitarbeitende(accessToken),
        listMonatsentwuerfe(accessToken, year, month),
      ]);
      setEmployees(employeeResult);
      setDrafts(draftResult);
      setSelectedEmployee((current) => employeeResult.some((item) => item.aktiv && item.id === current)
        ? current
        : employeeResult.find((item) => item.aktiv)?.id || "");
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lohnvorbereitung konnte nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { reload(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken, year, month]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion ist fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function submitEmployee(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      await createMitarbeiter(accessToken, { ...employeeForm, austrittsdatum: employeeForm.austrittsdatum || null });
      setEmployeeForm(EMPTY_EMPLOYEE);
      await reload();
    });
  }

  function startEditEmployee(item: Mitarbeiter) {
    setEditDraftId(null);
    setEditEmployeeId(item.id);
    setEditEmployeeForm(employeeToForm(item));
  }

  async function submitEditEmployee(event: FormEvent) {
    event.preventDefault();
    if (!editEmployeeId) return;
    await run(async () => {
      await updateMitarbeiter(accessToken, editEmployeeId, {
        vorname: editEmployeeForm.vorname,
        nachname: editEmployeeForm.nachname,
        eintrittsdatum: editEmployeeForm.eintrittsdatum,
        austrittsdatum: editEmployeeForm.austrittsdatum || null,
        monatsbrutto: editEmployeeForm.monatsbrutto,
      });
      setEditEmployeeId(null);
      await reload();
    });
  }

  async function deactivate(id: string) {
    await run(async () => { await deactivateMitarbeiter(accessToken, id); await reload(); });
  }

  async function reactivate(id: string) {
    await run(async () => { await reactivateMitarbeiter(accessToken, id); await reload(); });
  }

  async function submitDraft(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      await createMonatsentwurf(accessToken, {
        mitarbeiter_id: selectedEmployee,
        jahr: year,
        monat: month,
        grundbrutto: amounts.grundbrutto || null,
        steuerpflichtige_zuschlaege: amounts.steuerpflichtige_zuschlaege,
        steuerfreie_erstattungen: amounts.steuerfreie_erstattungen,
        sonstige_abzuege: amounts.sonstige_abzuege,
      });
      setAmounts({ grundbrutto: "", steuerpflichtige_zuschlaege: "0.00", steuerfreie_erstattungen: "0.00", sonstige_abzuege: "0.00" });
      await reload();
    });
  }

  function startEditDraft(item: Monatsentwurf) {
    setEditEmployeeId(null);
    setEditDraftId(item.id);
    setEditDraftForm(entwurfToForm(item));
  }

  async function submitEditDraft(event: FormEvent) {
    event.preventDefault();
    if (!editDraftId) return;
    const updates: MonatsentwurfUpdate = { ...editDraftForm };
    await run(async () => {
      await updateMonatsentwurf(accessToken, editDraftId, updates);
      setEditDraftId(null);
      await reload();
    });
  }

  async function abschliessen(id: string) {
    await run(async () => { await abschliessenMonatsentwurf(accessToken, id); await reload(); });
  }

  async function reaktivierenEntwurf(id: string) {
    await run(async () => { await reaktivierenMonatsentwurf(accessToken, id); await reload(); });
  }

  async function lohnzettel(item: Monatsentwurf) {
    await run(async () => {
      const blob = await downloadLohnzettel(accessToken, item.id);
      downloadBlob(blob, `Lohnzettel-${item.personalnummer}-${item.jahr}-${String(item.monat).padStart(2, "0")}.pdf`);
    });
  }

  async function exportMonth() {
    await run(async () => {
      downloadBlob(await downloadMonthExport(accessToken, year, month), `Lohnvorbereitung-${year}-${String(month).padStart(2, "0")}.csv`);
    });
  }

  if (loadStatus === "loading") return <PageState label="Lohnvorbereitung wird geladen …" />;
  if (loadStatus === "error") return <PageState label={error} error onRetry={reload} />;
  const activeEmployees = employees.filter((item) => item.aktiv);

  return (
    <div className="invoices-page">
      <PageHeader title="Lohnvorbereitung" description="Mitarbeiterdaten und monatliche Bruttowerte für die Steuerkanzlei vorbereiten." onBack={onBack} />

      <div className="compliance-boundary" role="note">
        <strong>Vorbereitung, keine Lohnabrechnung</strong>
        <p>Gesetzliche Steuern und Sozialabgaben werden noch nicht berechnet. Ein verbindlicher Abschluss oder elektronischer Versand ist bis zur amtlichen Systemprüfung gesperrt. „Abschließen" unten markiert nur, dass diese Vorbereitung fertig für die Steuerkanzlei ist.</p>
      </div>

      {error && <p className="auth-error" role="alert">{error}</p>}

      <form className="panel" onSubmit={submitEmployee}>
        <h2>Mitarbeitende Person anlegen</h2>
        <div className="field-row">
          <div><label htmlFor="employee-number">Personalnummer</label><input id="employee-number" value={employeeForm.personalnummer} onChange={(e) => setEmployeeForm({ ...employeeForm, personalnummer: e.target.value })} pattern="[A-Za-z0-9._-]+" required /></div>
          <div><label htmlFor="employee-first">Vorname</label><input id="employee-first" value={employeeForm.vorname} onChange={(e) => setEmployeeForm({ ...employeeForm, vorname: e.target.value })} required /></div>
          <div><label htmlFor="employee-last">Nachname</label><input id="employee-last" value={employeeForm.nachname} onChange={(e) => setEmployeeForm({ ...employeeForm, nachname: e.target.value })} required /></div>
        </div>
        <div className="field-row">
          <div><label htmlFor="employee-start">Eintritt</label><input id="employee-start" type="date" value={employeeForm.eintrittsdatum} onChange={(e) => setEmployeeForm({ ...employeeForm, eintrittsdatum: e.target.value })} required /></div>
          <div><label htmlFor="employee-end">Austritt (optional)</label><input id="employee-end" type="date" value={employeeForm.austrittsdatum} onChange={(e) => setEmployeeForm({ ...employeeForm, austrittsdatum: e.target.value })} /></div>
          <div><label htmlFor="employee-gross">Monatsbrutto</label><input id="employee-gross" type="number" min="0" step="0.01" value={employeeForm.monatsbrutto} onChange={(e) => setEmployeeForm({ ...employeeForm, monatsbrutto: e.target.value })} required /></div>
        </div>
        <button type="submit" disabled={busy}>Mitarbeitende Person speichern</button>
      </form>

      <h2 className="section-title">Mitarbeitende</h2>
      {employees.length === 0 ? <div className="empty-state"><h2>Noch keine Mitarbeitenden</h2><p className="auth-hint">Lege oben die erste Person für die Lohnvorbereitung an.</p></div> : (
        <div className="table-scroll"><table className="positions-table">
          <thead><tr><th>Personalnummer</th><th>Name</th><th>Beschäftigt seit</th><th>Monatsbrutto</th><th>Status</th><th /></tr></thead>
          <tbody>{employees.map((item) => (
            <Fragment key={item.id}>
              <tr>
                <td>{item.personalnummer}</td><td>{item.vorname} {item.nachname}</td><td>{formatDate(item.eintrittsdatum)}</td>
                <td className="number">{formatMoney(item.monatsbrutto)}</td><td><StatusPill status={item.aktiv ? "aktiv" : "inaktiv"} /></td>
                <td className="invoice-actions">
                  <button type="button" className="auth-link" disabled={busy} onClick={() => editEmployeeId === item.id ? setEditEmployeeId(null) : startEditEmployee(item)}>{editEmployeeId === item.id ? "Schließen" : "Bearbeiten"}</button>
                  {item.aktiv
                    ? <button type="button" className="auth-link danger" disabled={busy} onClick={() => deactivate(item.id)}>Deaktivieren</button>
                    : <button type="button" className="auth-link" disabled={busy} onClick={() => reactivate(item.id)}>Reaktivieren</button>}
                </td>
              </tr>
              {editEmployeeId === item.id && (
                <tr><td colSpan={6}>
                  <form className="confirm-row" onSubmit={submitEditEmployee}>
                    <div className="field-row">
                      <div><label htmlFor={`edit-emp-first-${item.id}`}>Vorname</label><input id={`edit-emp-first-${item.id}`} value={editEmployeeForm.vorname} onChange={(e) => setEditEmployeeForm({ ...editEmployeeForm, vorname: e.target.value })} required /></div>
                      <div><label htmlFor={`edit-emp-last-${item.id}`}>Nachname</label><input id={`edit-emp-last-${item.id}`} value={editEmployeeForm.nachname} onChange={(e) => setEditEmployeeForm({ ...editEmployeeForm, nachname: e.target.value })} required /></div>
                    </div>
                    <div className="field-row">
                      <div><label htmlFor={`edit-emp-start-${item.id}`}>Eintritt</label><input id={`edit-emp-start-${item.id}`} type="date" value={editEmployeeForm.eintrittsdatum} onChange={(e) => setEditEmployeeForm({ ...editEmployeeForm, eintrittsdatum: e.target.value })} required /></div>
                      <div><label htmlFor={`edit-emp-end-${item.id}`}>Austritt (optional)</label><input id={`edit-emp-end-${item.id}`} type="date" value={editEmployeeForm.austrittsdatum} onChange={(e) => setEditEmployeeForm({ ...editEmployeeForm, austrittsdatum: e.target.value })} /></div>
                      <div><label htmlFor={`edit-emp-gross-${item.id}`}>Monatsbrutto</label><input id={`edit-emp-gross-${item.id}`} type="number" min="0" step="0.01" value={editEmployeeForm.monatsbrutto} onChange={(e) => setEditEmployeeForm({ ...editEmployeeForm, monatsbrutto: e.target.value })} required /></div>
                    </div>
                    <button type="submit" disabled={busy}>Speichern</button>
                  </form>
                </td></tr>
              )}
            </Fragment>
          ))}</tbody>
        </table></div>
      )}

      <h2 className="section-title">Monat vorbereiten</h2>
      <form className="panel" onSubmit={submitDraft}>
        <div className="field-row">
          <div><label htmlFor="payroll-year">Jahr</label><select id="payroll-year" value={year} onChange={(e) => setYear(Number(e.target.value))}>{[now.getFullYear(), now.getFullYear() - 1].map((value) => <option key={value} value={value}>{value}</option>)}</select></div>
          <div><label htmlFor="payroll-month">Monat</label><select id="payroll-month" value={month} onChange={(e) => setMonth(Number(e.target.value))}>{Array.from({ length: 12 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{String(value).padStart(2, "0")}</option>)}</select></div>
          <div><label htmlFor="payroll-employee">Mitarbeitende Person</label><select id="payroll-employee" value={selectedEmployee} onChange={(e) => setSelectedEmployee(e.target.value)} required><option value="">Auswählen</option>{activeEmployees.map((item) => <option key={item.id} value={item.id}>{item.personalnummer} · {item.vorname} {item.nachname}</option>)}</select></div>
        </div>
        <div className="field-row">
          <div><label htmlFor="payroll-base">Grundbrutto (leer = Stammdaten)</label><input id="payroll-base" type="number" min="0" step="0.01" value={amounts.grundbrutto} onChange={(e) => setAmounts({ ...amounts, grundbrutto: e.target.value })} /></div>
          <div><label htmlFor="payroll-extra">Steuerpflichtige Zuschläge</label><input id="payroll-extra" type="number" min="0" step="0.01" value={amounts.steuerpflichtige_zuschlaege} onChange={(e) => setAmounts({ ...amounts, steuerpflichtige_zuschlaege: e.target.value })} required /></div>
        </div>
        <div className="field-row">
          <div><label htmlFor="payroll-refund">Steuerfreie Erstattungen</label><input id="payroll-refund" type="number" min="0" step="0.01" value={amounts.steuerfreie_erstattungen} onChange={(e) => setAmounts({ ...amounts, steuerfreie_erstattungen: e.target.value })} required /></div>
          <div><label htmlFor="payroll-deduction">Sonstige Abzüge</label><input id="payroll-deduction" type="number" min="0" step="0.01" value={amounts.sonstige_abzuege} onChange={(e) => setAmounts({ ...amounts, sonstige_abzuege: e.target.value })} required /></div>
        </div>
        <button type="submit" disabled={busy || activeEmployees.length === 0}>Monatsentwurf speichern</button>
      </form>

      <div className="section-heading-row"><h2 className="section-title">Entwürfe {String(month).padStart(2, "0")}/{year}</h2><button type="button" className="button-secondary" disabled={busy || drafts.length === 0} onClick={exportMonth}>CSV-Arbeitsdatei</button></div>
      {drafts.length === 0 ? <div className="empty-state"><h2>Noch kein Monatsentwurf</h2><p className="auth-hint">Erfasse für aktive Mitarbeitende die Bruttowerte dieses Monats.</p></div> : (
        <div className="table-scroll"><table className="positions-table">
          <thead><tr><th>Person</th><th>Status</th><th className="number">Gesamtbrutto</th><th className="number">Zwischensumme vor gesetzlichen Abgaben</th><th /></tr></thead>
          <tbody>{drafts.map((item) => (
            <Fragment key={item.id}>
              <tr>
                <td>{item.personalnummer} · {item.mitarbeiter_name}</td>
                <td>
                  <StatusPill status={item.status} />
                  {item.abgeschlossen_am && <div className="auth-hint">Abgeschlossen am {formatDate(item.abgeschlossen_am.slice(0, 10))}</div>}
                </td>
                <td className="number">{formatMoney(item.gesamtbrutto)}</td>
                <td className="number">{formatMoney(item.zwischenbetrag_vor_abgaben)}</td>
                <td className="invoice-actions">
                  {item.status === "vorbereitung" && (
                    <button type="button" className="auth-link" disabled={busy} onClick={() => editDraftId === item.id ? setEditDraftId(null) : startEditDraft(item)}>{editDraftId === item.id ? "Schließen" : "Korrigieren"}</button>
                  )}
                  <button type="button" className="auth-link" disabled={busy} onClick={() => lohnzettel(item)}>Lohnzettel</button>
                  {item.status === "vorbereitung"
                    ? <button type="button" className="auth-link" disabled={busy} onClick={() => abschliessen(item.id)}>Abschließen</button>
                    : <button type="button" className="auth-link" disabled={busy} onClick={() => reaktivierenEntwurf(item.id)}>Reaktivieren</button>}
                </td>
              </tr>
              {editDraftId === item.id && (
                <tr><td colSpan={5}>
                  <form className="confirm-row" onSubmit={submitEditDraft}>
                    <div className="field-row">
                      <div><label htmlFor={`edit-draft-base-${item.id}`}>Grundbrutto</label><input id={`edit-draft-base-${item.id}`} type="number" min="0" step="0.01" value={editDraftForm.grundbrutto} onChange={(e) => setEditDraftForm({ ...editDraftForm, grundbrutto: e.target.value })} required /></div>
                      <div><label htmlFor={`edit-draft-extra-${item.id}`}>Steuerpflichtige Zuschläge</label><input id={`edit-draft-extra-${item.id}`} type="number" min="0" step="0.01" value={editDraftForm.steuerpflichtige_zuschlaege} onChange={(e) => setEditDraftForm({ ...editDraftForm, steuerpflichtige_zuschlaege: e.target.value })} required /></div>
                    </div>
                    <div className="field-row">
                      <div><label htmlFor={`edit-draft-refund-${item.id}`}>Steuerfreie Erstattungen</label><input id={`edit-draft-refund-${item.id}`} type="number" min="0" step="0.01" value={editDraftForm.steuerfreie_erstattungen} onChange={(e) => setEditDraftForm({ ...editDraftForm, steuerfreie_erstattungen: e.target.value })} required /></div>
                      <div><label htmlFor={`edit-draft-deduction-${item.id}`}>Sonstige Abzüge</label><input id={`edit-draft-deduction-${item.id}`} type="number" min="0" step="0.01" value={editDraftForm.sonstige_abzuege} onChange={(e) => setEditDraftForm({ ...editDraftForm, sonstige_abzuege: e.target.value })} required /></div>
                    </div>
                    <button type="submit" disabled={busy}>Speichern</button>
                  </form>
                </td></tr>
              )}
            </Fragment>
          ))}</tbody>
        </table></div>
      )}
    </div>
  );
}
