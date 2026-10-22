import { useCallback, useEffect, useState } from "react";
import { initialAuthView } from "./entry";
import type { ReactNode } from "react";
import { Befehlspalette, type PaletteZiel } from "../../components/Befehlspalette";
import { Brand } from "../../components/Brand";
import { SearchIcon } from "../../components/icons";
import { BottomNav, type NavTarget } from "../../components/BottomNav";
import { PageState } from "../../components/PageState";
import { Sidebar } from "../../components/Sidebar";
import type { DesktopStep } from "../../lib/navTree";
import { ContactsPage } from "../invoices/ContactsPage";
import { GutschriftenPage } from "../invoices/GutschriftenPage";
import { InvoicesPage } from "../invoices/InvoicesPage";
import { MahnungenPage } from "../invoices/MahnungenPage";
import { WiederkehrendPage } from "../invoices/WiederkehrendPage";
import { QuotesPage } from "../quotes/QuotesPage";
import { AuftragsbestaetigungenPage } from "../auftraege/AuftragsbestaetigungenPage";
import { LieferscheinePage } from "../auftraege/LieferscheinePage";
import { ReceiptsPage } from "../receipts/ReceiptsPage";
import { WiederkehrendAusgabenPage } from "../receipts/WiederkehrendAusgabenPage";
import { AnlagenPage } from "../anlagen/AnlagenPage";
import { BankPage } from "../bank/BankPage";
import { ErsteSchrittePage } from "../erste-schritte/ErsteSchrittePage";
import { KassenbuchPage } from "../kassenbuch/KassenbuchPage";
import { CashflowPage } from "../reports/CashflowPage";
import { EuerPage } from "../reports/EuerPage";
import { BwaPage } from "../reports/BwaPage";
import { SusaPage } from "../reports/SusaPage";
import { UstvaPage } from "../reports/UstvaPage";
import { PayrollPage } from "../payroll/PayrollPage";
import { ProduktePage } from "../produkte/ProduktePage";
import { EinnahmenPage } from "../einnahmen/EinnahmenPage";
import { BuchhaltungseinstellungenPage } from "../buchhaltungseinstellungen/BuchhaltungseinstellungenPage";
import { ApiError, logout, me, type PreAuthResponse } from "./api";
import { AssistantPage } from "../ai/AssistantPage";
import { usePaletteKuerzel } from "../../lib/paletteKuerzel";
import { useAlertSichtbar } from "../../lib/alertSichtbar";
import { setUnauthorizedHandler } from "../../lib/session";
import { useRollenStatus } from "../../lib/useIstInhaber";
import { BenutzerPage } from "./BenutzerPage";
import { MfaEinrichtungPflicht } from "./MfaEinrichtungPflicht";
import { Dashboard } from "./Dashboard";
import { markiereMfaHinweis } from "../../lib/mfaHinweis";
import { LoginForm } from "./LoginForm";
import { MfaAnmeldung } from "./MfaAnmeldung";
import { PasswortVergessenForm } from "./PasswortVergessenForm";
import { PasswortZuruecksetzenForm } from "./PasswortZuruecksetzenForm";
import { resetTokenAusUrl } from "./passwortResetLink";
import { MandantSettingsPage } from "./MandantSettingsPage";
import { MorePage } from "./MorePage";
import { RegisterForm } from "./RegisterForm";
import { SteuerberaterPage } from "./SteuerberaterPage";
import { SecurityPrivacyPage } from "./SecurityPrivacyPage";
import { UmzugPage } from "../umzug/UmzugPage";

const TOKEN_STORAGE_KEY = "bilantiq_access_token";

function loadStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistToken(accessToken: string) {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
  } catch {
    // localStorage kann in privaten Fenstern o.ä. fehlschlagen — dann bleibt man
    // eben nach einem Reload ausgeloggt, kein Grund die App abstuerzen zu lassen.
  }
}

function clearStoredToken() {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // siehe persistToken
  }
}

export type Step =
  | { name: "register" }
  | { name: "login" }
  | { name: "passwort-vergessen" }
  | { name: "passwort-zuruecksetzen"; token: string }
  | { name: "restoring"; accessToken: string }
  | { name: "restore-error"; accessToken: string; message: string }
  | { name: "mfa-challenge"; preAuthToken: string }
  | { name: "mfa-einrichtung"; preAuthToken: string }
  | { name: "home"; accessToken: string }
  | { name: "assistant"; accessToken: string }
  | { name: "invoices"; accessToken: string; fokusId?: string; aktion?: "neu"; ansicht?: "altsystem" }
  | { name: "quotes"; accessToken: string; fokusId?: string }
  | { name: "receipts"; accessToken: string; fokusId?: string }
  | { name: "more"; accessToken: string }
  | { name: "euer"; accessToken: string }
  | { name: "cashflow"; accessToken: string }
  | { name: "ustva"; accessToken: string }
  | { name: "payroll"; accessToken: string }
  | { name: "settings"; accessToken: string }
  | { name: "contacts"; accessToken: string; fokusId?: string; aktion?: "neu" | "import" }
  | { name: "mahnungen"; accessToken: string }
  | { name: "susa"; accessToken: string }
  | { name: "bwa"; accessToken: string }
  | { name: "wiederkehrend"; accessToken: string }
  | { name: "gutschriften"; accessToken: string }
  | { name: "wiederkehrendAusgaben"; accessToken: string }
  | { name: "anlagen"; accessToken: string }
  | { name: "kassenbuch"; accessToken: string }
  | { name: "bank"; accessToken: string }
  | { name: "ersteSchritte"; accessToken: string }
  | { name: "benutzer"; accessToken: string }
  | { name: "security"; accessToken: string }
  | { name: "steuerberater"; accessToken: string }
  | { name: "auftragsbestaetigung"; accessToken: string }
  | { name: "lieferscheine"; accessToken: string }
  | { name: "rechnungsvorlage"; accessToken: string }
  | { name: "produkte"; accessToken: string; fokusId?: string; aktion?: "import" }
  | { name: "umzug"; accessToken: string }
  | { name: "einnahmen"; accessToken: string }
  | { name: "buchhaltungseinstellungen"; accessToken: string };

function activeTabFor(name: Step["name"]): NavTarget {
  switch (name) {
    case "invoices":
      return "invoices";
    case "receipts":
      return "receipts";
    case "quotes":
      return "quotes";
    case "assistant":
    case "more":
    case "euer":
    case "cashflow":
    case "ustva":
    case "payroll":
    case "settings":
    case "contacts":
    case "mahnungen":
    case "susa":
    case "bwa":
    case "wiederkehrend":
    case "gutschriften":
    case "wiederkehrendAusgaben":
    case "anlagen":
    case "bank":
    case "ersteSchritte":
    case "kassenbuch":
    case "benutzer":
    case "security":
    case "steuerberater":
    case "auftragsbestaetigung":
    case "lieferscheine":
    case "rechnungsvorlage":
    case "produkte":
    case "einnahmen":
    case "buchhaltungseinstellungen":
    case "umzug":
      return "more";
    default:
      return "home";
  }
}

function preAuthShell(children: ReactNode) {
  return (
    <>
      <a className="skip-link" href="#main-content">Zum Inhalt</a>
      <header className="topbar">
        <Brand />
        <span className="tagline">Zahlen klar. Kopf frei.</span>
      </header>
      <main id="main-content" className="app-shell app-shell--auth">{children}</main>
    </>
  );
}

export function AuthFlow() {
  const [step, setStep] = useState<Step>(() => {
    // Link aus der Passwort-Reset-Mail (URL-Fragment) hat Vorrang vor einer gespeicherten Sitzung.
    const resetToken = resetTokenAusUrl();
    if (resetToken) return { name: "passwort-zuruecksetzen", token: resetToken };
    const storedToken = loadStoredToken();
    return storedToken ? { name: "restoring", accessToken: storedToken } : { name: initialAuthView(window.location.search) };
  });

  const [paletteOffen, setPaletteOffen] = useState(false);
  const imShell = step.name !== "restoring" && step.name !== "restore-error" && "accessToken" in step;
  const paletteUmschalten = useCallback(() => setPaletteOffen((offen) => !offen), []);
  usePaletteKuerzel(imShell, paletteUmschalten);
  useEffect(() => { if (!imShell) setPaletteOffen(false); }, [imShell]);
  useAlertSichtbar(imShell);
  const shellToken = step.name !== "restoring" && step.name !== "restore-error" && "accessToken" in step ? step.accessToken : null;
  const istMitglied = useRollenStatus(shellToken) === "mitglied";

  // Zentral statt in jeder Seite einzeln: sonst haengt jede Seite ausser dem
  // Dashboard nach Ablauf des Tokens mit einer generischen Fehlermeldung fest,
  // statt zurueck zum Login zu fuehren (siehe die vielen api.ts-Module).
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearStoredToken();
      setStep({ name: "login" });
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    if (step.name !== "restoring") return;
    const accessToken = step.accessToken;
    let cancelled = false;
    me(accessToken)
      .then(() => {
        if (!cancelled) {
          setStep({ name: "home", accessToken });
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          clearStoredToken();
          setStep({ name: "login" });
        } else {
          // Netzwerkfehler oder Serverproblem: die Sitzung nicht verwerfen und nicht in die Registrierung fallen,
          // sondern erneut versuchen lassen (wichtig, wenn die installierte App ohne Netz gestartet wird).
          setStep({
            name: "restore-error",
            accessToken,
            message: err instanceof ApiError ? err.message : "Die Sitzung konnte nicht geladen werden.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.name === "restoring" ? step.accessToken : null]);

  function handlePreAuthResult(result: PreAuthResponse) {
    if (result.status === "mfa_optional" && result.access_token) {
      // Zwei-Faktor-Anmeldung ist optional: direkt hinein, das Dashboard empfiehlt die Einrichtung dringend.
      markiereMfaHinweis();
      persistToken(result.access_token);
      setStep({ name: "home", accessToken: result.access_token });
    } else if (result.status === "mfa_einrichtung_erforderlich") {
      // Pflicht-MFA noch nicht eingerichtet: nur der Einrichtungsbildschirm, keine Sitzung und kein Zugriff auf Daten.
      setStep({ name: "mfa-einrichtung", preAuthToken: result.pre_auth_token });
    } else {
      setStep({ name: "mfa-challenge", preAuthToken: result.pre_auth_token });
    }
  }

  /** Abmelden: erst den Server informieren (Sitzung wird dort ungueltig), aber ein Fehler dabei
   * (offline, Token schon abgelaufen) darf das lokale Abmelden nie verhindern. */
  function handleLogout(accessToken: string) {
    logout(accessToken).catch(() => {});
    clearStoredToken();
    setStep({ name: "login" });
  }

  function handleNavigate(target: NavTarget, accessToken: string) {
    switch (target) {
      case "home":
        setStep({ name: "home", accessToken });
        break;
      case "invoices":
        setStep({ name: "invoices", accessToken });
        break;
      case "receipts":
        setStep({ name: "receipts", accessToken });
        break;
      case "quotes":
        setStep({ name: "quotes", accessToken });
        break;
      case "more":
        setStep({ name: "more", accessToken });
        break;
    }
  }

  function handleDesktopNavigate(target: DesktopStep, accessToken: string, extra?: { fokusId?: string; aktion?: "neu" | "import"; ansicht?: "altsystem" }) {
    switch (target) {
      case "home":
        setStep({ name: "home", accessToken });
        break;
      case "assistant":
        setStep({ name: "assistant", accessToken });
        break;
      case "invoices":
        setStep({ name: "invoices", accessToken, fokusId: extra?.fokusId, aktion: extra?.aktion === "neu" ? "neu" : undefined, ansicht: extra?.ansicht });
        break;
      case "quotes":
        setStep({ name: "quotes", accessToken, fokusId: extra?.fokusId });
        break;
      case "receipts":
        setStep({ name: "receipts", accessToken, fokusId: extra?.fokusId });
        break;
      case "euer":
        setStep({ name: "euer", accessToken });
        break;
      case "cashflow":
        setStep({ name: "cashflow", accessToken });
        break;
      case "ustva":
        setStep({ name: "ustva", accessToken });
        break;
      case "payroll":
        setStep({ name: "payroll", accessToken });
        break;
      case "settings":
        setStep({ name: "settings", accessToken });
        break;
      case "contacts":
        setStep({ name: "contacts", accessToken, fokusId: extra?.fokusId, aktion: extra?.aktion });
        break;
      case "mahnungen":
        setStep({ name: "mahnungen", accessToken });
        break;
      case "susa":
        setStep({ name: "susa", accessToken });
        break;
      case "bwa":
        setStep({ name: "bwa", accessToken });
        break;
      case "wiederkehrend":
        setStep({ name: "wiederkehrend", accessToken });
        break;
      case "gutschriften":
        setStep({ name: "gutschriften", accessToken });
        break;
      case "wiederkehrendAusgaben":
        setStep({ name: "wiederkehrendAusgaben", accessToken });
        break;
      case "anlagen":
        setStep({ name: "anlagen", accessToken });
        break;
      case "ersteSchritte":
        setStep({ name: "ersteSchritte", accessToken });
        break;
      case "bank":
        setStep({ name: "bank", accessToken });
        break;
      case "kassenbuch":
        setStep({ name: "kassenbuch", accessToken });
        break;
      case "benutzer":
        setStep({ name: "benutzer", accessToken });
        break;
      case "security":
        setStep({ name: "security", accessToken });
        break;
      case "steuerberater":
        setStep({ name: "steuerberater", accessToken });
        break;
      case "auftragsbestaetigung":
        setStep({ name: "auftragsbestaetigung", accessToken });
        break;
      case "lieferscheine":
        setStep({ name: "lieferscheine", accessToken });
        break;
      case "rechnungsvorlage":
        setStep({ name: "rechnungsvorlage", accessToken });
        break;
      case "produkte":
        setStep({ name: "produkte", accessToken, fokusId: extra?.fokusId, aktion: extra?.aktion === "import" ? "import" : undefined });
        break;
      case "einnahmen":
        setStep({ name: "einnahmen", accessToken });
        break;
      case "buchhaltungseinstellungen":
        setStep({ name: "buchhaltungseinstellungen", accessToken });
        break;
      case "umzug":
        setStep({ name: "umzug", accessToken });
        break;
    }
  }

  switch (step.name) {
    case "restoring":
      return preAuthShell(<PageState label="Sitzung wird geladen …" />);
    case "restore-error": {
      const { accessToken, message } = step;
      return preAuthShell(
        <div className="page-state panel">
          <p className="auth-error" role="alert">{message}</p>
          <div className="actions">
            <button type="button" className="button-primary" onClick={() => setStep({ name: "restoring", accessToken })}>Erneut versuchen</button>
            <button type="button" className="button-secondary" onClick={() => { clearStoredToken(); setStep({ name: "login" }); }}>Zur Anmeldung</button>
          </div>
        </div>
      );
    }
    case "register":
      return preAuthShell(
        <RegisterForm
          onRegistered={handlePreAuthResult}
          onSwitchToLogin={() => setStep({ name: "login" })}
        />
      );
    case "login":
      return preAuthShell(
        <LoginForm
          onLoggedIn={handlePreAuthResult}
          onSwitchToRegister={() => setStep({ name: "register" })}
          onForgotPassword={() => setStep({ name: "passwort-vergessen" })}
        />
      );
    case "passwort-vergessen":
      return preAuthShell(<PasswortVergessenForm onZurueck={() => setStep({ name: "login" })} />);
    case "passwort-zuruecksetzen":
      return preAuthShell(
        <PasswortZuruecksetzenForm
          token={step.token}
          onZurAnmeldung={() => { clearStoredToken(); setStep({ name: "login" }); }}
          onNeuAnfordern={() => setStep({ name: "passwort-vergessen" })}
        />
      );
    case "mfa-challenge":
      return preAuthShell(
        <MfaAnmeldung
          preAuthToken={step.preAuthToken}
          onVerified={(accessToken) => { persistToken(accessToken); setStep({ name: "home", accessToken }); }}
        />
      );
    case "mfa-einrichtung":
      return preAuthShell(
        <MfaEinrichtungPflicht
          preAuthToken={step.preAuthToken}
          onFertig={(accessToken) => { persistToken(accessToken); setStep({ name: "home", accessToken }); }}
          onZurAnmeldung={() => { clearStoredToken(); setStep({ name: "login" }); }}
        />
      );
    case "home":
    case "assistant":
    case "invoices":
    case "quotes":
    case "receipts":
    case "more":
    case "euer":
    case "cashflow":
    case "ustva":
    case "payroll":
    case "settings":
    case "contacts":
    case "mahnungen":
    case "susa":
    case "bwa":
    case "wiederkehrend":
    case "gutschriften":
    case "wiederkehrendAusgaben":
    case "anlagen":
    case "bank":
    case "ersteSchritte":
    case "kassenbuch":
    case "benutzer":
    case "security":
    case "steuerberater":
    case "auftragsbestaetigung":
    case "lieferscheine":
    case "rechnungsvorlage":
    case "produkte":
    case "einnahmen":
    case "buchhaltungseinstellungen":
    case "umzug": {
      const { accessToken } = step;
      let content: ReactNode;
      switch (step.name) {
        case "home":
          content = (
            <Dashboard
              accessToken={accessToken}
              onSessionExpired={() => { clearStoredToken(); setStep({ name: "login" }); }}
              onOpenInvoices={() => setStep({ name: "invoices", accessToken })}
              onOpenReceipts={() => setStep({ name: "receipts", accessToken })}
              onOpenUstva={() => setStep({ name: "ustva", accessToken })}
              onOpenKassenbuch={() => setStep({ name: "kassenbuch", accessToken })}
              onOpenSecurity={() => setStep({ name: "security", accessToken })}
            />
          );
          break;
        case "assistant":
          content = <AssistantPage accessToken={accessToken} onBack={() => setStep({ name: "home", accessToken })} />;
          break;
        case "invoices":
          content = (
            <InvoicesPage
              key={`${step.fokusId ?? ""}|${step.aktion ?? ""}|${step.ansicht ?? ""}`}
              accessToken={accessToken}
              onBack={() => setStep({ name: "home", accessToken })}
              fokusId={step.fokusId}
              startMitNeu={step.aktion === "neu"}
              startAnsicht={step.ansicht}
            />
          );
          break;
        case "quotes":
          content = <QuotesPage key={step.fokusId ?? ""} accessToken={accessToken} onBack={() => setStep({ name: "home", accessToken })} fokusId={step.fokusId} />;
          break;
        case "receipts":
          content = <ReceiptsPage key={step.fokusId ?? ""} accessToken={accessToken} onBack={() => setStep({ name: "home", accessToken })} fokusId={step.fokusId} />;
          break;
        case "more":
          content = (
            <MorePage
              onOpenAssistant={() => setStep({ name: "assistant", accessToken })}
              onOpenEuer={() => setStep({ name: "euer", accessToken })}
              onOpenCashflow={() => setStep({ name: "cashflow", accessToken })}
              onOpenUstva={() => setStep({ name: "ustva", accessToken })}
              onOpenPayroll={() => setStep({ name: "payroll", accessToken })}
              onOpenSettings={() => setStep({ name: "settings", accessToken })}
              onOpenContacts={() => setStep({ name: "contacts", accessToken })}
              onOpenProdukte={() => setStep({ name: "produkte", accessToken })}
              onOpenUmzug={() => setStep({ name: "umzug", accessToken })}
              onOpenEinnahmen={() => setStep({ name: "einnahmen", accessToken })}
              onOpenBuchhaltungseinstellungen={() => setStep({ name: "buchhaltungseinstellungen", accessToken })}
              onOpenMahnungen={() => setStep({ name: "mahnungen", accessToken })}
              onOpenSusa={() => setStep({ name: "susa", accessToken })}
              onOpenBwa={() => setStep({ name: "bwa", accessToken })}
              onOpenWiederkehrend={() => setStep({ name: "wiederkehrend", accessToken })}
              onOpenGutschriften={() => setStep({ name: "gutschriften", accessToken })}
              onOpenWiederkehrendAusgaben={() => setStep({ name: "wiederkehrendAusgaben", accessToken })}
              onOpenAnlagen={() => setStep({ name: "anlagen", accessToken })}
              onOpenKassenbuch={() => setStep({ name: "kassenbuch", accessToken })}
              onOpenBank={() => setStep({ name: "bank", accessToken })}
              onOpenErsteSchritte={() => setStep({ name: "ersteSchritte", accessToken })}
              onOpenBenutzer={() => setStep({ name: "benutzer", accessToken })}
              onOpenSecurity={() => setStep({ name: "security", accessToken })}
              onOpenSteuerberater={() => setStep({ name: "steuerberater", accessToken })}
              onOpenAuftragsbestaetigung={() => setStep({ name: "auftragsbestaetigung", accessToken })}
              onOpenLieferscheine={() => setStep({ name: "lieferscheine", accessToken })}
              onOpenRechnungsvorlage={() => setStep({ name: "rechnungsvorlage", accessToken })}
              onLogout={() => handleLogout(accessToken)}
              istMitglied={istMitglied}
            />
          );
          break;
        case "euer":
          content = <EuerPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "cashflow":
          content = <CashflowPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "ustva":
          content = <UstvaPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "payroll":
          content = <PayrollPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "settings":
          content = <MandantSettingsPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "contacts":
          content = <ContactsPage key={`${step.fokusId ?? ""}|${step.aktion ?? ""}`} accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} fokusId={step.fokusId} startAktion={step.aktion} />;
          break;
        case "mahnungen":
          content = <MahnungenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "susa":
          content = <SusaPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "bwa":
          content = <BwaPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "wiederkehrend":
          content = <WiederkehrendPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "gutschriften":
          content = <GutschriftenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "wiederkehrendAusgaben":
          content = <WiederkehrendAusgabenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "anlagen":
          content = <AnlagenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "ersteSchritte":
          content = (
            <ErsteSchrittePage
              accessToken={accessToken}
              onBack={() => setStep({ name: "more", accessToken })}
              onOpen={(ziel) => handleDesktopNavigate(ziel as DesktopStep, accessToken)}
            />
          );
          break;
        case "bank":
          content = <BankPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "kassenbuch":
          content = <KassenbuchPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "benutzer":
          content = <BenutzerPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "security":
          content = (
            <SecurityPrivacyPage
              accessToken={accessToken}
              onBack={() => setStep({ name: "more", accessToken })}
              onSecurityInvalidated={() => { clearStoredToken(); setStep({ name: "login" }); }}
              onDeleted={() => { clearStoredToken(); setStep({ name: "login" }); }}
            />
          );
          break;
        case "steuerberater":
          content = (
            <SteuerberaterPage
              accessToken={accessToken}
              onBack={() => setStep({ name: "more", accessToken })}
              onOpenEuer={() => setStep({ name: "euer", accessToken })}
              onOpenUstva={() => setStep({ name: "ustva", accessToken })}
              onOpenSusa={() => setStep({ name: "susa", accessToken })}
              onOpenBwa={() => setStep({ name: "bwa", accessToken })}
            />
          );
          break;
        case "auftragsbestaetigung":
          content = <AuftragsbestaetigungenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "lieferscheine":
          content = <LieferscheinePage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "rechnungsvorlage":
          content = (
            <InvoicesPage
              accessToken={accessToken}
              onBack={() => setStep({ name: "more", accessToken })}
              startInEditor
              initialTab="design"
            />
          );
          break;
        case "produkte":
          content = <ProduktePage key={`${step.fokusId ?? ""}|${step.aktion ?? ""}`} accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} fokusId={step.fokusId} startAktion={step.aktion} />;
          break;
        case "einnahmen":
          content = <EinnahmenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "buchhaltungseinstellungen":
          content = <BuchhaltungseinstellungenPage accessToken={accessToken} onBack={() => setStep({ name: "more", accessToken })} />;
          break;
        case "umzug":
          content = (
            <UmzugPage
              accessToken={accessToken}
              onBack={() => setStep({ name: "more", accessToken })}
              onOpen={(ziel) => handleDesktopNavigate(ziel.step as DesktopStep, accessToken, { aktion: ziel.aktion, ansicht: ziel.ansicht })}
            />
          );
          break;
      }
      return (
        <>
          <a className="skip-link" href="#main-content">Zum Inhalt</a>
          <header className="topbar topbar--shell">
            <Brand />
            <span className="tagline">Zahlen klar. Kopf frei.</span>
            <button type="button" className="topbar-suche" onClick={() => setPaletteOffen(true)} aria-label="Suche und Schnellaktionen öffnen">
              <SearchIcon width={20} height={20} aria-hidden="true" />
            </button>
          </header>
          {/* Vor dem Inhalt im DOM: Die Sidebar steht links, die Tab-Reihenfolge soll der Lesereihenfolge folgen. */}
          <Sidebar active={step.name} onNavigate={(target) => handleDesktopNavigate(target, accessToken)} onSuche={() => setPaletteOffen(true)} onLogout={() => handleLogout(accessToken)} istMitglied={istMitglied} />
          <main id="main-content" className="app-shell">{content}</main>
          <BottomNav active={activeTabFor(step.name)} onNavigate={(target) => handleNavigate(target, accessToken)} />
          {paletteOffen && (
            <Befehlspalette
              accessToken={accessToken}
              onSchliessen={() => setPaletteOffen(false)}
              onWaehle={(ziel: PaletteZiel) => {
                setPaletteOffen(false);
                handleDesktopNavigate(ziel.step, accessToken, { fokusId: ziel.fokusId, aktion: ziel.aktion, ansicht: ziel.ansicht });
              }}
            />
          )}
        </>
      );
    }
  }
}
