import { useEffect, useRef, useState } from "react";
import { BarChart } from "../../components/BarChart";
import { DonutChart } from "../../components/DonutChart";
import { InvoiceIcon, ScanIcon, BankIcon, TaxIcon } from "../../components/icons";
import { getDashboard, type Dashboard as DashboardData } from "../reports/api";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatMoney } from "../../lib/format";
import { ApiError, me, type MeResponse } from "./api";

interface Props {
  accessToken: string;
  onSessionExpired: () => void;
  onOpenInvoices: () => void;
  onOpenReceipts: () => void;
  onOpenUstva: () => void;
  onOpenKassenbuch: () => void;
  onOpenSecurity: () => void;
}

import { MfaHinweis } from "./MfaHinweis";

const MONATSNAMEN = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

const AKTION_LABELS: Record<string, string> = {
  registrierung: "Konto registriert",
  mfa_aktiviert: "Zwei-Faktor-Anmeldung eingerichtet",
  login_erfolgreich: "Angemeldet",
  mandant_aktualisiert: "Firmendaten geändert",
  logo_hochgeladen: "Logo hochgeladen",
  logo_entfernt: "Logo entfernt",
  passwort_geaendert: "Passwort geändert",
  mitglied_direkt_angelegt: "Benutzer angelegt",
  mitglied_entfernt: "Benutzer entfernt",
  einladung_erstellt: "Einladung erstellt",
  rechnung_finalisiert: "Rechnung abgeschlossen",
  rechnung_storniert: "Rechnung storniert",
  rechnung_bezahlt_markiert: "Rechnung als bezahlt markiert",
  // Historische Eintraege der entfernten Online-Zahlung bleiben im Audit-Log lesbar.
  rechnung_zahllink_erstellt: "Zahllink erstellt",
  rechnung_checkout_geoeffnet: "Online-Zahlung geöffnet",
  rechnung_online_bezahlt: "Rechnung online bezahlt",
  rechnung_onlinezahlung_fehlgeschlagen: "Online-Zahlung fehlgeschlagen",
  rechnung_onlinezahlung_nach_manueller_markierung: "Online-Zahlung nach manueller Buchung eingegangen",
  angebot_versendet: "Angebot versendet",
  angebot_angenommen: "Angebot angenommen",
  angebot_abgelehnt: "Angebot abgelehnt",
  angebot_umgewandelt: "Angebot in Rechnung umgewandelt",
  auftragsbestaetigung_erstellt: "Auftragsbestätigung erstellt",
  lieferschein_erstellt: "Lieferschein erstellt",
  kassenbuch_buchung: "Kassenbuch-Buchung",
  e_rechnung_erzeugt: "E-Rechnung erzeugt",
  zugferd_pdf_erzeugt: "ZUGFeRD-PDF erzeugt",
  beleg_hochgeladen: "Beleg hochgeladen",
  beleg_gebucht: "Beleg gebucht",
  mahnung_erstellt: "Mahnung erstellt",
  loeschantrag: "Löschantrag gestellt",
  login_fehlgeschlagen: "Anmeldung fehlgeschlagen",
  mfa_code_falsch: "Falscher Zwei-Faktor-Code",
  mitarbeiter_angelegt: "Mitarbeiter angelegt",
  mitarbeiter_deaktiviert: "Mitarbeiter deaktiviert",
  lohn_monatsentwurf_angelegt: "Lohn-Monatsentwurf angelegt",
  wiederkehrende_rechnungen_erzeugt: "Wiederkehrende Rechnungen erzeugt",
  wiederkehrende_ausgaben_erzeugt: "Wiederkehrende Ausgaben erzeugt",
};

function aktionLabel(aktion: string): string {
  return AKTION_LABELS[aktion] ?? aktion.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function formatZeitpunkt(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString("de-DE")} · ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`;
}

export function Dashboard({ accessToken, onSessionExpired, onOpenInvoices, onOpenReceipts, onOpenUstva, onOpenKassenbuch, onOpenSecurity }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [versuch, setVersuch] = useState(0);
  // AuthFlow übergibt bei jedem Rendern eine neue Funktion. Als Effekt-Abhängigkeit würde das Dashboard bei jedem Öffnen
  // und Schließen der Suchpalette neu laden.
  const sitzungAbgelaufenRef = useRef(onSessionExpired);
  useEffect(() => { sitzungAbgelaufenRef.current = onSessionExpired; });

  useEffect(() => {
    let cancelled = false;
    Promise.all([me(accessToken), getDashboard(accessToken, new Date().getFullYear())])
      .then(([profileResult, dashboardResult]) => {
        if (cancelled) return;
        setProfile(profileResult);
        setDashboard(dashboardResult);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          sitzungAbgelaufenRef.current();
          return;
        }
        setError(err instanceof ApiError ? err.message : "Übersicht konnte nicht geladen werden.");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, versuch]);

  if (status === "loading") {
    return (
      <div className="dashboard-page">
        <PageState label="Übersicht wird geladen …" />
      </div>
    );
  }

  if (status === "error" || !profile || !dashboard) {
    return (
      <div className="dashboard-page">
        <PageState label={error} error onRetry={() => { setStatus("loading"); setVersuch((n) => n + 1); }} />
      </div>
    );
  }

  const initial = profile.firmenname.trim().charAt(0).toUpperCase() || "?";
  const grenzeProzent = Math.min(100, (Number(dashboard.umsatz_brutto_jahr) / Number(dashboard.kleinunternehmergrenze)) * 100);

  return (
    <div className="dashboard-page">
      <MfaHinweis onEinrichten={onOpenSecurity} />
      <div className="dashboard-topbar">
        <div className="dashboard-avatar">{initial}</div>
        <div className="dashboard-topbar-text">
          <div className="name">{profile.firmenname}</div>
          <div className="email">Angemeldet als {profile.rolle}</div>
        </div>
      </div>

      <PageHeader title={`Herzlich willkommen, ${profile.firmenname.split(" ")[0]}`} description="Deine wichtigsten Zahlen für das laufende Geschäftsjahr." />

      <div className="quick-actions">
        <button type="button" className="button-primary" onClick={onOpenInvoices}><InvoiceIcon width={18} /> Rechnung schreiben</button>
        <button type="button" onClick={onOpenReceipts}><ScanIcon width={18} /> Ausgabe hochladen</button>
        <button type="button" onClick={onOpenInvoices}><BankIcon width={18} /> Zahlungen zuordnen</button>
        <button type="button" onClick={onOpenUstva}><TaxIcon width={18} /> UStVA vorbereiten</button>
      </div>

      <div className="panel dashboard-summary">
        <p className="dashboard-summary-label">Gewinn vor Steuern ({dashboard.jahr})</p>
        <p className="dashboard-summary-value">{formatMoney(dashboard.gewinn_vor_steuern)}</p>
        <div className="dashboard-summary-legend">
          <div className="dashboard-summary-legend-item dashboard-summary-legend-item--einnahmen">
            Einnahmen
            <span className="dashboard-summary-legend-value">{formatMoney(dashboard.einnahmen)}</span>
          </div>
          <div className="dashboard-summary-legend-item dashboard-summary-legend-item--ausgaben">
            Ausgaben
            <span className="dashboard-summary-legend-value">{formatMoney(dashboard.ausgaben)}</span>
          </div>
        </div>

        <BarChart
          daten={dashboard.monatswerte.map((m) => ({ label: MONATSNAMEN[m.monat - 1], a: Number(m.einnahmen), b: Number(m.ausgaben) }))}
          labelA="Einnahmen" labelB="Ausgaben"
        />

        <div className="dashboard-summary-footer">
          <span className="auth-hint" style={{ margin: 0 }}>{dashboard.hinweis}</span>
          <div className="dashboard-summary-footer-links">
            <button type="button" className="auth-link" onClick={onOpenInvoices}>Rechnung schreiben →</button>
            <button type="button" className="auth-link" onClick={onOpenReceipts}>Ausgabe erfassen →</button>
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="panel">
          <h2 className="panel-title">Ausstehende Rechnungen</h2>
          <p className="dashboard-summary-label">Offener Betrag</p>
          <p className="dashboard-summary-value receivables-value">
            {formatMoney((Number(dashboard.faellige_rechnungen.betrag) + Number(dashboard.offene_rechnungen.betrag)).toFixed(2))}
          </p>
          {dashboard.faellige_rechnungen.anzahl > 0 && (
            <p className="auth-hint" style={{ color: "var(--danger)", margin: 0 }}>
              {dashboard.faellige_rechnungen.anzahl} überfällig ({formatMoney(dashboard.faellige_rechnungen.betrag)})
            </p>
          )}
          {dashboard.offene_rechnungen.anzahl > 0 && (
            <p className="auth-hint" style={{ margin: "4px 0 0" }}>
              {dashboard.offene_rechnungen.anzahl} noch nicht fällig ({formatMoney(dashboard.offene_rechnungen.betrag)})
            </p>
          )}
          {dashboard.faellige_rechnungen.anzahl === 0 && dashboard.offene_rechnungen.anzahl === 0 && (
            <p className="auth-hint" style={{ margin: 0 }}>Keine offenen Rechnungen.</p>
          )}
          <button type="button" className="auth-link panel-footer-action" onClick={onOpenInvoices}>Rechnungen ansehen →</button>
        </div>

        <div className="panel">
          <h2 className="panel-title">Kleinunternehmergrenze</h2>
          <p className="dashboard-summary-label">Umsatz {dashboard.jahr}</p>
          <p className="dashboard-summary-value">{formatMoney(dashboard.umsatz_brutto_jahr)}</p>
          <div className="grenze-balken"><div className="grenze-balken-fuellung" style={{ width: `${grenzeProzent}%` }} /></div>
          <div className="grenze-balken-labels">
            <span>0 €</span>
            <span>Grenze {formatMoney(dashboard.kleinunternehmergrenze)}</span>
          </div>
          <p className="auth-hint" style={{ margin: "8px 0 0" }}>
            Gilt für die Kleinunternehmerregelung nach §19 UStG, falls du diese nutzt.
          </p>
        </div>

        <div className="panel">
          <h2 className="panel-title">Kassenbuch</h2>
          <p className="dashboard-summary-label">Aktueller Bestand</p>
          <p className="dashboard-summary-value">{formatMoney(dashboard.kassenbestand)}</p>
          <p className="auth-hint" style={{ margin: 0 }}>Nur manuelle Bar-Buchungen — keine Kontoanbindung.</p>
          <button type="button" className="auth-link panel-footer-action" onClick={onOpenKassenbuch}>Kassenbuch öffnen →</button>
        </div>

        <div className="panel">
          <h2 className="panel-title">Top 5 Kunden</h2>
          <DonutChart
            daten={dashboard.top_kunden.map((k) => ({ name: k.name, wert: Number(k.betrag) }))}
            leerHinweis="Noch keine bezahlten Rechnungen vorhanden."
          />
        </div>

        <div className="panel">
          <h2 className="panel-title">Top 5 Ausgaben</h2>
          <DonutChart
            daten={dashboard.top_ausgaben_kategorien.map((k) => ({ name: k.name, wert: Number(k.betrag) }))}
            leerHinweis="Noch keine Ausgaben gebucht."
          />
        </div>

        <div className="panel">
          <h2 className="panel-title">Verlauf</h2>
          {dashboard.verlauf.length === 0 ? (
            <p className="auth-hint" style={{ margin: 0 }}>Noch keine Aktivität.</p>
          ) : (
            <ul className="verlauf-liste">
              {dashboard.verlauf.map((e, i) => (
                <li key={i}>
                  <span className="verlauf-aktion">{aktionLabel(e.aktion)}</span>
                  {e.kontext && <span className="verlauf-kontext">{e.kontext}</span>}
                  <span className="verlauf-zeit">{formatZeitpunkt(e.zeitpunkt)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
