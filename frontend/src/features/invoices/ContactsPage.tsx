import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { useFokus } from "../../lib/useFokus";
import { useIstInhaber } from "../../lib/useIstInhaber";
import { ApiError } from "../auth/api";
import { KontaktHistorie } from "../altrechnungen/KontaktHistorie";
import { ImportAssistent } from "../stammdaten/ImportAssistent";
import { StammdatenAktionen } from "../stammdaten/StammdatenAktionen";
import {
  archiviereKontakt, createKontakt, listKontakte, loescheKontakt, stelleKontaktWiederHer, updateKontakt, type Kontakt,
} from "./api";
import { KontaktFelder } from "./KontaktFelder";
import { formularZuEingabe, kontaktZuFormular, LEERES_KONTAKT_FORMULAR, type KontaktFormular } from "./kontaktFormular";

interface Props {
  accessToken: string;
  onBack: () => void;
  /** Kontakt, zu dem die Suche gesprungen ist (wird geoeffnet und markiert) */
  fokusId?: string;
  /** Schnellaktion aus der Befehlspalette */
  startAktion?: "neu" | "import";
}

type Ansicht = "alle" | "kunde" | "lieferant" | "archiv";

const ANSICHTEN: { wert: Ansicht; label: string }[] = [
  { wert: "alle", label: "Alle" },
  { wert: "kunde", label: "Kunden" },
  { wert: "lieferant", label: "Lieferanten" },
  { wert: "archiv", label: "Archiv" },
];

const TYP_LABEL = { kunde: "Kunde", lieferant: "Lieferant", beide: "Kunde und Lieferant" } as const;

function filterFuer(ansicht: Ansicht) {
  if (ansicht === "archiv") return { archiviert: true };
  if (ansicht === "alle") return {};
  return { typ: ansicht };
}

function ansprechpartner(kontakt: Kontakt): string {
  return [kontakt.anrede, kontakt.vorname, kontakt.nachname].filter(Boolean).join(" ");
}

function passtZurSuche(kontakt: Kontakt, suche: string): boolean {
  if (!suche) return true;
  const heuhaufen = [
    kontakt.name, kontakt.ort, kontakt.plz, kontakt.email, kontakt.kundennummer, kontakt.telefon, kontakt.vorname, kontakt.nachname,
  ].filter(Boolean).join(" ").toLocaleLowerCase("de");
  return suche.toLocaleLowerCase("de").split(/\s+/).every((wort) => heuhaufen.includes(wort));
}

export function ContactsPage({ accessToken, onBack, fokusId, startAktion }: Props) {
  const [loadStatus, setLoadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [hinweis, setHinweis] = useState("");
  const [ansicht, setAnsicht] = useState<Ansicht>("alle");
  const [suche, setSuche] = useState("");
  const [kontakte, setKontakte] = useState<Kontakt[]>([]);
  const [neuOffen, setNeuOffen] = useState(startAktion === "neu");
  const [createForm, setCreateForm] = useState<KontaktFormular>(LEERES_KONTAKT_FORMULAR);
  const [creating, setCreating] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<KontaktFormular>(LEERES_KONTAKT_FORMULAR);
  const [saving, setSaving] = useState(false);
  const [loeschenBestaetigen, setLoeschenBestaetigen] = useState(false);
  const [importOffen, setImportOffen] = useState(startAktion === "import");
  const istInhaber = useIstInhaber(accessToken);

  async function load(aktuelleAnsicht: Ansicht = ansicht) {
    setError("");
    try {
      const liste = await listKontakte(accessToken, filterFuer(aktuelleAnsicht));
      setKontakte(liste);
      setLoadStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kontakte konnten nicht geladen werden.");
      setLoadStatus("error");
    }
  }

  useEffect(() => { load(ansicht); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken, ansicht]);

  const sichtbar = useMemo(() => kontakte.filter((kontakt) => passtZurSuche(kontakt, suche.trim())), [kontakte, suche]);

  // Sprung aus der Suche: Kontakt oeffnen; archivierte liegen im Archiv-Reiter und werden dort gesucht.
  const fokusErledigt = useRef<string | null>(null);
  useEffect(() => {
    if (!fokusId || loadStatus !== "ready" || fokusErledigt.current === fokusId) return;
    const treffer = kontakte.find((k) => k.id === fokusId);
    if (treffer) {
      fokusErledigt.current = fokusId;
      startEdit(treffer);
    } else if (ansicht !== "archiv") {
      setAnsicht("archiv");
    } else {
      fokusErledigt.current = fokusId; // gibt es nicht (mehr)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fokusId, loadStatus, kontakte]);
  useFokus(fokusId, loadStatus === "ready" && kontakte.some((k) => k.id === fokusId));

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      const neu = await createKontakt(accessToken, formularZuEingabe(createForm));
      setCreateForm(LEERES_KONTAKT_FORMULAR);
      setNeuOffen(false);
      setHinweis(`${neu.name} wurde angelegt.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kontakt konnte nicht angelegt werden.");
    } finally {
      setCreating(false);
    }
  }

  function startEdit(kontakt: Kontakt) {
    setEditId(kontakt.id);
    setEditForm(kontaktZuFormular(kontakt));
    setLoeschenBestaetigen(false);
    setHinweis("");
  }

  async function aktion(ausfuehren: () => Promise<unknown>, meldung: string, fehler: string) {
    setSaving(true);
    setError("");
    try {
      await ausfuehren();
      setEditId(null);
      setHinweis(meldung);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fehler);
    } finally {
      setSaving(false);
      setLoeschenBestaetigen(false);
    }
  }

  function handleSaveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editId) return;
    aktion(() => updateKontakt(accessToken, editId, formularZuEingabe(editForm)), "Gespeichert.", "Kontakt konnte nicht gespeichert werden.");
  }

  if (loadStatus === "loading") return <PageState label="Kontakte werden geladen …" />;
  if (loadStatus === "error" && kontakte.length === 0) return <PageState label={error} error onRetry={() => load()} />;

  return (
    <div className="invoices-page">
      <PageHeader
        title="Kontakte" description="Kunden und Lieferanten für Rechnungen, Angebote und den Kontoabgleich." onBack={onBack}
        action={
          <div className="page-header-aktionen">
            <StammdatenAktionen
              accessToken={accessToken} ziel="kontakte" istInhaber={istInhaber} onFehler={setError}
              onImportieren={() => { setImportOffen(true); setNeuOffen(false); setHinweis(""); }}
            />
            {!neuOffen && !importOffen && (
              <button type="button" className="button-primary" onClick={() => setNeuOffen(true)}>Neuer Kontakt</button>
            )}
          </div>
        }
      />

      {error && <p className="auth-error" role="alert">{error}</p>}
      {hinweis && <p className="auth-hint" role="status">{hinweis}</p>}

      {importOffen && (
        <ImportAssistent
          accessToken={accessToken} ziel="kontakte"
          onAbbrechen={() => setImportOffen(false)}
          onFertig={() => { setImportOffen(false); setAnsicht("alle"); void load("alle"); }}
        />
      )}

      {neuOffen && (
        <form className="panel" onSubmit={handleCreate}>
          <h2>Neuer Kontakt</h2>
          <KontaktFelder form={createForm} onChange={setCreateForm} idPrefix="new" />
          <div className="actions">
            <button type="submit" disabled={creating}>{creating ? "Wird angelegt …" : "Kontakt anlegen"}</button>
            <button type="button" className="auth-link" onClick={() => setNeuOffen(false)} disabled={creating}>Abbrechen</button>
          </div>
        </form>
      )}

      <div className="liste-kopf">
        <div className="pill-row" role="tablist" aria-label="Kontakte filtern">
          {ANSICHTEN.map((eintrag) => (
            <button
              key={eintrag.wert} type="button" role="tab" aria-selected={ansicht === eintrag.wert}
              className={`pill${ansicht === eintrag.wert ? " pill--aktiv" : ""}`}
              onClick={() => { setAnsicht(eintrag.wert); setEditId(null); setHinweis(""); }}
            >
              {eintrag.label}
            </button>
          ))}
        </div>
        <input
          type="search" className="liste-suche" placeholder="Name, Ort, E-Mail oder Nummer" aria-label="Kontakte durchsuchen"
          value={suche} onChange={(e) => setSuche(e.target.value)}
        />
      </div>

      {sichtbar.length === 0 ? (
        <div className="empty-state">
          <h2>{suche ? "Keine Treffer" : ansicht === "archiv" ? "Das Archiv ist leer" : "Noch keine Kontakte"}</h2>
          <p className="auth-hint" style={{ margin: 0 }}>
            {suche ? "Versuche einen anderen Suchbegriff." : ansicht === "archiv"
              ? "Archivierte Kontakte bleiben für alte Rechnungen erhalten und erscheinen nicht in Auswahllisten."
              : "Lege den ersten Kontakt an oder übernimm deine Kunden und Lieferanten aus einer Excel- oder CSV-Datei."}
          </p>
          {!suche && ansicht !== "archiv" && kontakte.length === 0 && !importOffen && (
            <div className="actions">
              <button type="button" className="button-primary" onClick={() => setNeuOffen(true)}>Kontakt anlegen</button>
              {istInhaber && (
                <button type="button" className="auth-link" onClick={() => setImportOffen(true)}>Aus Excel oder altem Programm übernehmen</button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="table-scroll">
          <table className="positions-table">
            <thead>
              <tr><th>Name</th><th>Ort</th><th>Kontakt</th><th>Art</th><th /></tr>
            </thead>
            <tbody>
              {sichtbar.map((kontakt) => (
                <Fragment key={kontakt.id}>
                  <tr data-fokus-id={kontakt.id}>
                    <td>
                      {kontakt.name}
                      {ansprechpartner(kontakt) && <div className="zelle-nebentext">{ansprechpartner(kontakt)}</div>}
                    </td>
                    <td>{[kontakt.plz, kontakt.ort].filter(Boolean).join(" ") || "—"}</td>
                    <td>
                      {kontakt.email || kontakt.telefon || "—"}
                      {kontakt.email && kontakt.telefon && <div className="zelle-nebentext">{kontakt.telefon}</div>}
                    </td>
                    <td>{TYP_LABEL[kontakt.typ ?? "kunde"]}{kontakt.ist_geschaeftskunde ? "" : " (privat)"}</td>
                    <td>
                      <button type="button" className="auth-link" onClick={() => (editId === kontakt.id ? setEditId(null) : startEdit(kontakt))}>
                        {editId === kontakt.id ? "Schließen" : "Bearbeiten"}
                      </button>
                    </td>
                  </tr>
                  {editId === kontakt.id && (
                    <tr>
                      <td colSpan={5}>
                        <form className="confirm-row" onSubmit={handleSaveEdit}>
                          <KontaktFelder form={editForm} onChange={setEditForm} idPrefix={`edit-${kontakt.id}`} />
                          <KontaktHistorie accessToken={accessToken} kontaktId={kontakt.id} />
                          <div className="actions">
                            <button type="submit" disabled={saving}>{saving ? "Wird gespeichert …" : "Speichern"}</button>
                            {kontakt.archiviert ? (
                              <button
                                type="button" className="auth-link" disabled={saving}
                                onClick={() => aktion(() => stelleKontaktWiederHer(accessToken, kontakt.id), `${kontakt.name} ist wieder aktiv.`, "Wiederherstellen fehlgeschlagen.")}
                              >
                                Wiederherstellen
                              </button>
                            ) : (
                              <button
                                type="button" className="auth-link" disabled={saving}
                                onClick={() => aktion(() => archiviereKontakt(accessToken, kontakt.id), `${kontakt.name} wurde archiviert.`, "Archivieren fehlgeschlagen.")}
                              >
                                Archivieren
                              </button>
                            )}
                            {loeschenBestaetigen ? (
                              <button
                                type="button" className="auth-link danger" disabled={saving}
                                onClick={() => aktion(() => loescheKontakt(accessToken, kontakt.id), `${kontakt.name} wurde gelöscht.`, "Löschen fehlgeschlagen.")}
                              >
                                Wirklich löschen
                              </button>
                            ) : (
                              <button type="button" className="auth-link" disabled={saving} onClick={() => setLoeschenBestaetigen(true)}>
                                Löschen
                              </button>
                            )}
                          </div>
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
