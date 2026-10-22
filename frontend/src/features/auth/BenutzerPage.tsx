import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate } from "../../lib/format";
import {
  ApiError, createEinladung, entferneMitglied, erstelleMitgliedDirekt, listEinladungen, listMitglieder, me,
  widerrufeEinladung, type Einladung, type Mitglied, type MitgliedDirekt,
} from "./api";

interface Props { accessToken: string; onBack: () => void }

export function BenutzerPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [istOwner, setIstOwner] = useState(false);
  const [eigeneUserId, setEigeneUserId] = useState("");
  const [mitglieder, setMitglieder] = useState<Mitglied[]>([]);
  const [einladungen, setEinladungen] = useState<Einladung[]>([]);
  const [inviting, setInviting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [neuerCode, setNeuerCode] = useState<string | null>(null);

  const [neueEmail, setNeueEmail] = useState("");
  const [neueRolle, setNeueRolle] = useState<"mitglied" | "owner">("mitglied");
  const [anlegeStatus, setAnlegeStatus] = useState<"idle" | "loading" | "error">("idle");
  const [angelegtesMitglied, setAngelegtesMitglied] = useState<MitgliedDirekt | null>(null);

  async function load() {
    setStatus("loading");
    setError("");
    try {
      const profil = await me(accessToken);
      setEigeneUserId(profil.user_id);
      setIstOwner(profil.rolle === "owner");
      const [mitgliederListe, einladungenListe] = await Promise.all([
        listMitglieder(accessToken),
        profil.rolle === "owner" ? listEinladungen(accessToken) : Promise.resolve([]),
      ]);
      setMitglieder(mitgliederListe);
      setEinladungen(einladungenListe);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Benutzer konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

  async function handleInvite() {
    setInviting(true);
    setError("");
    setNeuerCode(null);
    try {
      const einladung = await createEinladung(accessToken, "mitglied");
      setNeuerCode(einladung.code);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Einladung konnte nicht erstellt werden.");
    } finally {
      setInviting(false);
    }
  }

  async function handleWiderrufen(id: string) {
    setBusyId(id);
    setError("");
    try {
      await widerrufeEinladung(accessToken, id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Widerrufen ist fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleEntfernen(userId: string) {
    setBusyId(userId);
    setError("");
    try {
      await entferneMitglied(accessToken, userId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Entfernen ist fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDirektAnlegen(event: FormEvent) {
    event.preventDefault();
    setAnlegeStatus("loading");
    setError("");
    setAngelegtesMitglied(null);
    try {
      const mitglied = await erstelleMitgliedDirekt(accessToken, neueEmail, neueRolle);
      setAngelegtesMitglied(mitglied);
      setNeueEmail("");
      setAnlegeStatus("idle");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Benutzer konnte nicht angelegt werden.");
      setAnlegeStatus("error");
    }
  }

  if (status === "loading") return <PageState label="Benutzer werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={load} />;

  const offeneEinladungen = einladungen.filter((e) => !e.widerrufen && !e.eingeloest_am);

  return (
    <div className="invoices-page">
      <PageHeader title="Benutzer" description="Wer Zugriff auf diesen Mandanten hat." onBack={onBack} />

      {error && <p className="auth-error" role="alert">{error}</p>}

      <h2 className="section-title">Mitglieder</h2>
      <div className="table-scroll">
        <table className="positions-table">
          <thead><tr><th>E-Mail</th><th>Rolle</th><th /></tr></thead>
          <tbody>
            {mitglieder.map((m) => (
              <tr key={m.user_id}>
                <td>{m.email}</td>
                <td>{m.rolle === "owner" ? "Owner" : "Mitglied"}</td>
                <td>
                  {istOwner && m.user_id !== eigeneUserId && (
                    <button type="button" className="auth-link danger" disabled={busyId === m.user_id} onClick={() => handleEntfernen(m.user_id)}>
                      Entfernen
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {istOwner && (
        <>
          <h2 className="section-title">Direkt anlegen</h2>
          <form className="panel" onSubmit={handleDirektAnlegen}>
            <p className="auth-hint">
              Legt sofort ein Konto an, statt einen Einladungscode zu erzeugen. Kein E-Mail-Versand — das
              Erstpasswort wird nur einmal hier angezeigt, gib es der Person selbst weiter.
            </p>
            {angelegtesMitglied && (
              <p className="hinweis">
                {angelegtesMitglied.email} wurde angelegt. Erstpasswort: <strong>{angelegtesMitglied.initial_passwort}</strong>
                {" "}— wird nicht erneut angezeigt.
              </p>
            )}
            <div className="field-row">
              <div>
                <label htmlFor="benutzer-email">E-Mail</label>
                <input
                  id="benutzer-email" type="email" value={neueEmail}
                  onChange={(e) => setNeueEmail(e.target.value)} required
                />
              </div>
              <div>
                <label htmlFor="benutzer-rolle">Rolle</label>
                <select id="benutzer-rolle" value={neueRolle} onChange={(e) => setNeueRolle(e.target.value as "mitglied" | "owner")}>
                  <option value="mitglied">Mitglied</option>
                  <option value="owner">Owner</option>
                </select>
              </div>
            </div>
            <button type="submit" disabled={anlegeStatus === "loading"}>
              {anlegeStatus === "loading" ? "Wird angelegt …" : "Benutzer anlegen"}
            </button>
          </form>

          <h2 className="section-title">Einladen</h2>
          <div className="panel">
            <p className="auth-hint">
              Kein E-Mail-Versand — du gibst den Code selbst weiter. Die Person registriert sich damit und
              tritt direkt diesem Mandanten als Mitglied bei, statt eine eigene Firma anzulegen.
            </p>
            {neuerCode && (
              <p className="hinweis">Neuer Code: <strong>{neuerCode}</strong> — gültig 7 Tage.</p>
            )}
            <button type="button" onClick={handleInvite} disabled={inviting}>
              {inviting ? "Wird erstellt …" : "Neuen Einladungscode erzeugen"}
            </button>
          </div>

          {offeneEinladungen.length > 0 && (
            <>
              <h2 className="section-title">Offene Einladungen</h2>
              <div className="table-scroll">
                <table className="positions-table">
                  <thead><tr><th>Code</th><th>Rolle</th><th>Gültig bis</th><th /></tr></thead>
                  <tbody>
                    {offeneEinladungen.map((e) => (
                      <tr key={e.id}>
                        <td>{e.code}</td>
                        <td>{e.rolle === "owner" ? "Owner" : "Mitglied"}</td>
                        <td>{formatDate(e.ablauf_am.slice(0, 10))}</td>
                        <td>
                          <button type="button" className="auth-link danger" disabled={busyId === e.id} onClick={() => handleWiderrufen(e.id)}>
                            Widerrufen
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}


    </div>
  );
}
