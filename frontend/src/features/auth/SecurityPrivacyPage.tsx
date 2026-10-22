import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate } from "../../lib/format";
import {
  ApiError,
  confirmEmailChange,
  deleteAccount,
  fetchDatenexport,
  getSecurityOverview,
  passwortAendern,
  revokeOtherSessions,
  revokeSession,
  startEmailChange,
  startMfaReset,
  deactivateMfa,
  startMfaSetup,
} from "./api";
import { confirmMfaResetMitCodes, type SecurityOverviewMitCodes } from "./sicherheitApi";
import { WiederherstellungscodesAnzeige } from "./WiederherstellungscodesAnzeige";
import { WiederherstellungscodesVerwaltung } from "./WiederherstellungscodesVerwaltung";

interface Props {
  accessToken: string;
  onBack: () => void;
  onSecurityInvalidated: () => void;
  onDeleted: () => void;
}

export function SecurityPrivacyPage({ accessToken, onBack, onSecurityInvalidated, onDeleted }: Props) {
  const [data, setData] = useState<SecurityOverviewMitCodes | null>(null);
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const [aktuellesPasswort, setAktuellesPasswort] = useState("");
  const [neuesPasswort, setNeuesPasswort] = useState("");
  const [passwortWiederholung, setPasswortWiederholung] = useState("");

  const [emailNeu, setEmailNeu] = useState("");
  const [emailPasswort, setEmailPasswort] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [emailCodeGesendet, setEmailCodeGesendet] = useState(false);

  const [loeschPasswort, setLoeschPasswort] = useState("");
  const [loeschCode, setLoeschCode] = useState("");
  const [mfaPasswort, setMfaPasswort] = useState("");
  const [mfaAltCode, setMfaAltCode] = useState("");
  const [mfaNeuCode, setMfaNeuCode] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaUri, setMfaUri] = useState("");
  // Wiederherstellungscodes der ersten Aktivierung: werden einmalig angezeigt, bevor die Sitzung endet.
  const [neueWiederherstellungscodes, setNeueWiederherstellungscodes] = useState<string[] | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function load() {
    setLoadStatus("loading");
    setError("");
    try {
      setData(await getSecurityOverview(accessToken));
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sicherheitsdaten konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (neuesPasswort !== passwortWiederholung) {
      setError("Die Passwort-Wiederholung stimmt nicht überein.");
      return;
    }
    setBusy("password");
    try {
      await passwortAendern(accessToken, aktuellesPasswort, neuesPasswort);
      onSecurityInvalidated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Passwort konnte nicht geändert werden.");
      setBusy(null);
    }
  }

  async function requestEmailChange(event: FormEvent) {
    event.preventDefault();
    setBusy("email-start");
    setError("");
    try {
      await startEmailChange(accessToken, emailNeu, emailPasswort);
      setEmailCodeGesendet(true);
      setBusy(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "E-Mail-Änderung konnte nicht gestartet werden.");
      setBusy(null);
    }
  }

  async function finishEmailChange(event: FormEvent) {
    event.preventDefault();
    setBusy("email-confirm");
    setError("");
    try {
      await confirmEmailChange(accessToken, emailCode);
      onSecurityInvalidated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "E-Mail-Adresse konnte nicht bestätigt werden.");
      setBusy(null);
    }
  }

  async function disableMfa() {
    if (!mfaPasswort || mfaAltCode.trim().length < 6) {
      setError("Zum Deaktivieren brauchst du dein Passwort und den aktuellen Code (oder einen Wiederherstellungscode).");
      return;
    }
    setBusy("mfa-off");
    setError("");
    try {
      await deactivateMfa(accessToken, mfaPasswort, mfaAltCode);
      onSecurityInvalidated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Zwei-Faktor-Anmeldung konnte nicht deaktiviert werden.");
      setBusy(null);
    }
  }

  async function beginMfaSetup() {
    setBusy("mfa-start");
    setError("");
    try {
      const result = await startMfaSetup(accessToken);
      setMfaSecret(result.secret);
      setMfaUri(result.provisioning_uri);
      setBusy(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Zwei-Faktor-Anmeldung konnte nicht eingerichtet werden.");
      setBusy(null);
    }
  }

  async function beginMfaReset(event: FormEvent) {
    event.preventDefault();
    setBusy("mfa-start");
    setError("");
    try {
      const result = await startMfaReset(accessToken, mfaPasswort, mfaAltCode);
      setMfaSecret(result.secret);
      setMfaUri(result.provisioning_uri);
      setBusy(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "MFA konnte nicht neu eingerichtet werden.");
      setBusy(null);
    }
  }

  async function finishMfaReset(event: FormEvent) {
    event.preventDefault();
    setBusy("mfa-confirm");
    setError("");
    try {
      const ergebnis = await confirmMfaResetMitCodes(accessToken, mfaNeuCode);
      if (ergebnis?.wiederherstellungscodes?.length) {
        // Erste Aktivierung: erst die Codes zeigen, danach (nach Bestätigung) neu anmelden.
        setNeueWiederherstellungscodes(ergebnis.wiederherstellungscodes);
        setBusy(null);
      } else {
        onSecurityInvalidated();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Neuer MFA-Code konnte nicht bestätigt werden.");
      setBusy(null);
    }
  }

  async function logoutOtherSessions() {
    setBusy("sessions");
    setError("");
    try {
      await revokeOtherSessions(accessToken);
      await load();
      setBusy(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Andere Sitzungen konnten nicht abgemeldet werden.");
      setBusy(null);
    }
  }

  async function logoutSession(id: string) {
    setBusy(id);
    setError("");
    try {
      await revokeSession(accessToken, id);
      await load();
      setBusy(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sitzung konnte nicht abgemeldet werden.");
      setBusy(null);
    }
  }

  async function exportData() {
    setBusy("export");
    setError("");
    try {
      const blob = await fetchDatenexport(accessToken);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `bilantiq-datenexport-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setBusy(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Datenexport ist fehlgeschlagen.");
      setBusy(null);
    }
  }

  async function removeAccount(event: FormEvent) {
    event.preventDefault();
    setBusy("delete");
    setError("");
    try {
      await deleteAccount(accessToken, loeschPasswort, data?.mfa_enabled ? loeschCode.trim() : undefined);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Konto konnte nicht gelöscht werden.");
      setBusy(null);
    }
  }

  if (loadStatus === "loading") return <PageState label="Sicherheit wird geladen …" />;
  if (loadStatus === "error" || !data) return <PageState label={error} error onRetry={load} />;

  if (neueWiederherstellungscodes) {
    return (
      <div className="invoices-page">
        <PageHeader title="Zwei-Faktor-Anmeldung aktiviert" description="Bewahre jetzt deine Wiederherstellungscodes auf." />
        <section className="panel">
          <WiederherstellungscodesAnzeige codes={neueWiederherstellungscodes} weiterLabel="Weiter und neu anmelden" onWeiter={onSecurityInvalidated} />
        </section>
      </div>
    );
  }

  return (
    <div className="invoices-page">
      <PageHeader
        title="Sicherheit & Datenschutz"
        description="Login-Daten, Zwei-Faktor-Anmeldung, Sitzungen und Datenschutzfunktionen."
        onBack={onBack}
      />
      {error && <p className="auth-error" role="alert">{error}</p>}

      <h2 className="section-title">E-Mail-Adresse</h2>
      <section className="panel">
        <p>Aktuell: <strong>{data.email}</strong></p>
        {!emailCodeGesendet ? (
          <form onSubmit={requestEmailChange}>
            <div className="field-row">
              <div><label htmlFor="sec-email-neu">Neue E-Mail</label><input id="sec-email-neu" type="email" autoComplete="email" value={emailNeu} onChange={(e) => setEmailNeu(e.target.value)} required /></div>
              <div><label htmlFor="sec-email-passwort">Aktuelles Passwort</label><input id="sec-email-passwort" type="password" autoComplete="current-password" value={emailPasswort} onChange={(e) => setEmailPasswort(e.target.value)} required /></div>
            </div>
            <button type="submit" disabled={busy !== null}>Bestätigungscode senden</button>
          </form>
        ) : (
          <form onSubmit={finishEmailChange}>
            <p className="auth-hint">Ein 6-stelliger Code wurde an die neue Adresse gesendet. Er ist 15 Minuten gültig.</p>
            <label htmlFor="sec-email-code">Bestätigungscode</label>
            <input id="sec-email-code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={emailCode} onChange={(e) => setEmailCode(e.target.value)} required />
            <button type="submit" disabled={busy !== null}>E-Mail ändern und neu anmelden</button>
          </form>
        )}
      </section>

      <h2 className="section-title">Passwort</h2>
      <form className="panel" onSubmit={changePassword}>
        <p className="auth-hint">
          Mindestens 12 Zeichen. Nach der Änderung werden alle Sitzungen widerrufen und eine neue Anmeldung ist erforderlich.
        </p>
        <label htmlFor="sec-pw-aktuell">Aktuelles Passwort</label>
        <input id="sec-pw-aktuell" type="password" autoComplete="current-password" value={aktuellesPasswort} onChange={(e) => setAktuellesPasswort(e.target.value)} required />
        <div className="field-row">
          <div><label htmlFor="sec-pw-neu">Neues Passwort</label><input id="sec-pw-neu" type="password" autoComplete="new-password" minLength={12} value={neuesPasswort} onChange={(e) => setNeuesPasswort(e.target.value)} required /></div>
          <div><label htmlFor="sec-pw-wdh">Neues Passwort wiederholen</label><input id="sec-pw-wdh" type="password" autoComplete="new-password" minLength={12} value={passwortWiederholung} onChange={(e) => setPasswortWiederholung(e.target.value)} required /></div>
        </div>
        <button type="submit" disabled={busy !== null}>Passwort ändern</button>
      </form>

      <h2 className="section-title">Zwei-Faktor-Anmeldung</h2>
      <section className="panel">
        <p>Status: <strong>{data.mfa_enabled ? "Aktiv" : "Nicht aktiv"}</strong></p>
        {!mfaSecret && !data.mfa_enabled ? (
          <>
            <p className="auth-hint">
              Mit Zwei-Faktor-Anmeldung ist dein Konto auch dann geschützt, wenn jemand dein Passwort kennt. Wir empfehlen sie dringend,
              weil in Bilantiq deine Geschäftsdaten liegen.
            </p>
            <button type="button" onClick={beginMfaSetup} disabled={busy !== null}>Zwei-Faktor-Anmeldung einrichten</button>
          </>
        ) : !mfaSecret ? (
          <form onSubmit={beginMfaReset}>
            <p className="auth-hint">Eine Neueinrichtung benötigt zusätzlich zum Passwort einen gültigen Code deiner aktuellen Authenticator-App.</p>
            <div className="field-row">
              <div><label htmlFor="sec-mfa-passwort">Aktuelles Passwort</label><input id="sec-mfa-passwort" type="password" autoComplete="current-password" value={mfaPasswort} onChange={(e) => setMfaPasswort(e.target.value)} required /></div>
              <div><label htmlFor="sec-mfa-altcode">Aktueller Code (6 Stellen) oder Wiederherstellungscode</label><input id="sec-mfa-altcode" autoComplete="one-time-code" maxLength={32} value={mfaAltCode} onChange={(e) => setMfaAltCode(e.target.value)} required /></div>
            </div>
            <div className="actions">
              <button type="submit" disabled={busy !== null}>MFA neu einrichten</button>
              <button type="button" className="button-secondary" onClick={disableMfa} disabled={busy !== null}>MFA deaktivieren</button>
            </div>
            <p className="auth-hint">Beim Deaktivieren schützt nur noch dein Passwort das Konto. Alle Sitzungen werden beendet und du meldest dich neu an.</p>
          </form>
        ) : (
          <form onSubmit={finishMfaReset}>
            <div className="mfa-secret"><span className="mfa-secret-label">Neues Secret</span><code>{mfaSecret}</code></div>
            <a className="auth-link" href={mfaUri}>In Authenticator-App öffnen</a>
            <p className="auth-hint">
              {data.mfa_enabled
                ? "Die bisherige MFA bleibt aktiv, bis der neue Code erfolgreich bestätigt wurde."
                : "Nach der Bestätigung musst du dich einmal neu anmelden und gibst dann bei jeder Anmeldung einen Code ein."}
            </p>
            <label htmlFor="sec-mfa-neucode">Code der neuen Einrichtung</label>
            <input id="sec-mfa-neucode" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={mfaNeuCode} onChange={(e) => setMfaNeuCode(e.target.value)} required />
            <button type="submit" disabled={busy !== null}>Code bestätigen und neu anmelden</button>
          </form>
        )}
        {data.mfa_enabled && !mfaSecret && (
          <WiederherstellungscodesVerwaltung accessToken={accessToken} offen={data.wiederherstellungscodes_offen} onGeaendert={load} />
        )}
      </section>

      <h2 className="section-title">Aktive Sitzungen</h2>
      <section className="panel">
        <button type="button" className="button-secondary" onClick={logoutOtherSessions} disabled={busy !== null}>Alle anderen Sitzungen abmelden</button>
        <div className="security-session-list">
          {data.sessions.map((session) => (
            <div className="security-session" key={session.id}>
              <div>
                <strong>{session.aktuell ? "Aktuelle Sitzung" : "Angemeldetes Gerät"}</strong>
                <p className="auth-hint">{session.user_agent || "Unbekannter Client"} · seit {formatDate(session.erstellt_am.slice(0, 10))}</p>
              </div>
              {!session.aktuell && <button type="button" className="auth-link danger" onClick={() => logoutSession(session.id)} disabled={busy !== null}>Abmelden</button>}
            </div>
          ))}
        </div>
      </section>

      <h2 className="section-title">Datenschutz</h2>
      <section className="panel">
        <p className="auth-hint">Datenexport nach DSGVO Art. 15/20. Der Export ist nur im eingeloggten Zustand abrufbar.</p>
        <button type="button" className="button-secondary" onClick={exportData} disabled={busy !== null}>Meine Daten exportieren</button>
      </section>

      <div className="danger-zone">
        <h2>Konto löschen</h2>
        {!confirmDelete ? (
          <button type="button" className="auth-link danger" onClick={() => setConfirmDelete(true)}>Konto löschen</button>
        ) : (
          <form className="delete-confirm" onSubmit={removeAccount}>
            <p>Deine Stammdaten werden anonymisiert. Gesetzlich aufzubewahrende Buchungsdaten bleiben entsprechend der bestehenden Aufbewahrungslogik erhalten. Das lässt sich nicht rückgängig machen.</p>
            <div className="field-row">
              <div>
                <label htmlFor="sec-loesch-passwort">Aktuelles Passwort</label>
                <input id="sec-loesch-passwort" type="password" autoComplete="current-password" value={loeschPasswort} onChange={(e) => setLoeschPasswort(e.target.value)} required />
              </div>
              {data.mfa_enabled && (
                <div>
                  <label htmlFor="sec-loesch-code">Aktueller Code (6 Stellen)</label>
                  <input id="sec-loesch-code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={loeschCode} onChange={(e) => setLoeschCode(e.target.value)} required />
                </div>
              )}
            </div>
            <div className="delete-confirm-actions">
              <button type="submit" className="danger" disabled={busy !== null}>Endgültig löschen</button>
              <button type="button" className="auth-link" onClick={() => { setConfirmDelete(false); setLoeschPasswort(""); setLoeschCode(""); }} disabled={busy !== null}>Abbrechen</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
