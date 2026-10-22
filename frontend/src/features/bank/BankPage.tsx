import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { formatDate, formatMoney } from "../../lib/format";
import { listeAltrechnungen } from "../altrechnungen/api";
import { ApiError } from "../auth/api";
import { listInvoices } from "../invoices/api";
import { listAusgaben, listBelege } from "../receipts/api";
import {
  bestaetigeSichere, createKonto, getZusammenfassung, hebeZuordnungAuf, ignoriereUmsatz, listKonten, listUmsaetze,
  ordneZu, type Bankkonto, type ImportErgebnis, type Umsatz, type UmsatzFilter, type Vorschlag, type Zusammenfassung,
} from "./api";
import { ImportPanel } from "./ImportPanel";

interface Props { accessToken: string; onBack: () => void }

interface Kandidat { typ: Vorschlag["typ"]; id: string; label: string }

const FILTER: { wert: UmsatzFilter; label: (z: Zusammenfassung | null) => string }[] = [
  { wert: "offen", label: (z) => `Offen${z ? ` (${z.offen})` : ""}` },
  { wert: "beleg_fehlt", label: (z) => `Beleg fehlt${z ? ` (${z.beleg_fehlt})` : ""}` },
  { wert: "zugeordnet", label: () => "Zugeordnet" },
  { wert: "ignoriert", label: () => "Ignoriert" },
];

const ZIEL_LABEL: Record<Vorschlag["typ"], string> = { rechnung: "Rechnung", altrechnung: "Rechnung aus dem alten Programm", beleg: "Beleg", ausgabe: "Ausgabe" };

async function ladeKandidaten(accessToken: string, umsatz: Umsatz): Promise<Kandidat[]> {
  if (Number(umsatz.betrag) > 0) {
    const [rechnungen, alt] = await Promise.all([
      listInvoices(accessToken),
      listeAltrechnungen(accessToken).then((antwort) => antwort.eintraege).catch(() => []),
    ]);
    return [
      ...rechnungen
        .filter((r) => r.status === "final" && !r.bezahlt_am && r.nummer)
        .map((r) => ({
          typ: "rechnung" as const, id: r.id,
          label: `${r.nummer}, ${r.kontakt_name}, ${formatMoney(r.brutto_gesamt)}`,
        })),
      ...alt
        .filter((a) => Number(a.offen) > 0)
        .map((a) => ({
          typ: "altrechnung" as const, id: a.id,
          label: `Altes Programm: ${a.nummer}, ${a.kontakt_name}, offen ${formatMoney(a.offen)}`,
        })),
    ];
  }
  const [belege, ausgaben] = await Promise.all([listBelege(accessToken), listAusgaben(accessToken)]);
  return [
    ...belege.filter((b) => b.status !== "gebucht").map((b) => ({
      typ: "beleg" as const, id: b.id,
      label: `Beleg: ${b.anbieter.wert ?? "ohne Anbieter"}${b.betrag.wert ? `, ${formatMoney(b.betrag.wert)}` : ""}`,
    })),
    ...ausgaben.map((a) => ({
      typ: "ausgabe" as const, id: a.id,
      label: `Gebucht: ${a.anbieter}, ${formatMoney(a.betrag)}, ${formatDate(a.datum)}`,
    })),
  ];
}

function UmsatzZeile({
  accessToken, umsatz, ausgewaehlt, onToggle, onChanged, onError,
}: {
  accessToken: string; umsatz: Umsatz; ausgewaehlt: boolean;
  onToggle: () => void; onChanged: () => void; onError: (meldung: string) => void;
}) {
  const [arbeitet, setArbeitet] = useState(false);
  const [modus, setModus] = useState<"" | "waehlen" | "ignorieren">("");
  const [kandidaten, setKandidaten] = useState<Kandidat[] | null>(null);
  const [auswahl, setAuswahl] = useState("");
  const [grund, setGrund] = useState("");
  const eingang = Number(umsatz.betrag) > 0;
  const vorschlag = umsatz.vorschlag;

  async function ausfuehren(aktion: () => Promise<unknown>, fehlerText: string) {
    setArbeitet(true);
    onError("");
    try {
      await aktion();
      setModus("");
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : fehlerText);
    } finally {
      setArbeitet(false);
    }
  }

  async function zeigeAuswahl() {
    setModus("waehlen");
    if (kandidaten) return;
    try {
      const liste = await ladeKandidaten(accessToken, umsatz);
      setKandidaten(liste);
      setAuswahl(liste[0] ? `${liste[0].typ}:${liste[0].id}` : "");
    } catch (err) {
      setModus("");
      onError(err instanceof ApiError ? err.message : "Die Auswahl konnte nicht geladen werden.");
    }
  }

  const aktionen = (() => {
    if (umsatz.status === "zugeordnet") {
      return umsatz.zuordnung_typ === "rechnung" || umsatz.zuordnung_typ === "altrechnung" ? null : (
        <button type="button" className="auth-link" disabled={arbeitet}
          onClick={() => ausfuehren(() => hebeZuordnungAuf(accessToken, umsatz.id), "Das Aufheben ist fehlgeschlagen.")}>
          Aufheben
        </button>
      );
    }
    if (umsatz.status === "ignoriert") {
      return (
        <button type="button" className="auth-link" disabled={arbeitet}
          onClick={() => ausfuehren(() => hebeZuordnungAuf(accessToken, umsatz.id), "Das Aufheben ist fehlgeschlagen.")}>
          Wieder öffnen
        </button>
      );
    }
    return (
      <>
        {vorschlag && (
          <button type="button" disabled={arbeitet}
            onClick={() => ausfuehren(() => ordneZu(accessToken, umsatz.id, vorschlag.typ, vorschlag.ziel_id), "Das Zuordnen ist fehlgeschlagen.")}>
            Zuordnen
          </button>
        )}
        <button type="button" className="auth-link" disabled={arbeitet} onClick={zeigeAuswahl}>
          {vorschlag ? "Andere wählen" : "Zuordnen …"}
        </button>
        <button type="button" className="auth-link" disabled={arbeitet} onClick={() => setModus("ignorieren")}>Ignorieren</button>
      </>
    );
  })();

  return (
    <>
      <tr>
        <td>
          {vorschlag?.sicher && umsatz.status === "offen" && (
            <input type="checkbox" checked={ausgewaehlt} onChange={onToggle} aria-label="Sicheren Vorschlag auswählen" />
          )}
        </td>
        <td>{formatDate(umsatz.buchungsdatum)}</td>
        <td>
          <div>{umsatz.gegenpartei_name ?? "Ohne Namen"}</div>
          {umsatz.verwendungszweck && <div className="bank-zweck">{umsatz.verwendungszweck}</div>}
        </td>
        <td className={`number ${eingang ? "bank-eingang" : ""}`}>{eingang ? "+" : ""}{formatMoney(umsatz.betrag)}</td>
        <td>
          {umsatz.status === "offen" && vorschlag && (
            <div title={vorschlag.gruende.join(". ")}>
              <span className={`status-pill ${vorschlag.sicher ? "status-pill--ok" : "status-pill--warn"}`}>
                {vorschlag.sicher ? "Sicher" : "Vorschlag"}
              </span>{" "}
              {ZIEL_LABEL[vorschlag.typ]}: {vorschlag.anzeige}
              <div className="bank-zweck">{vorschlag.gruende.join(". ")}.</div>
            </div>
          )}
          {umsatz.status === "offen" && !vorschlag && (
            <span className="status-pill status-pill--neutral">{eingang ? "Keine passende offene Rechnung" : "Beleg fehlt"}</span>
          )}
          {umsatz.status === "zugeordnet" && (
            <span className="status-pill status-pill--ok">Zugeordnet{umsatz.zuordnung_typ ? `: ${ZIEL_LABEL[umsatz.zuordnung_typ]}` : ""}</span>
          )}
          {umsatz.status === "ignoriert" && (
            <span className="status-pill status-pill--neutral">Ignoriert{umsatz.ignoriert_grund ? `: ${umsatz.ignoriert_grund}` : ""}</span>
          )}
        </td>
        <td><div className="invoice-actions">{aktionen}</div></td>
      </tr>
      {modus === "waehlen" && (
        <tr><td colSpan={6}>
          {kandidaten === null ? <p className="auth-hint">Wird geladen …</p> : kandidaten.length === 0 ? (
            <p className="auth-hint">
              {eingang ? "Es gibt keine offene Rechnung zum Zuordnen." : "Es gibt keinen offenen Beleg und keine Ausgabe zum Zuordnen."}
            </p>
          ) : (
            <div className="bank-auswahl">
              <select value={auswahl} onChange={(e) => setAuswahl(e.target.value)} aria-label="Ziel der Zuordnung">
                {kandidaten.map((k) => <option key={`${k.typ}:${k.id}`} value={`${k.typ}:${k.id}`}>{k.label}</option>)}
              </select>
              <button type="button" className="button-primary" disabled={arbeitet || !auswahl}
                onClick={() => {
                  const [typ, ...rest] = auswahl.split(":");
                  ausfuehren(() => ordneZu(accessToken, umsatz.id, typ as Vorschlag["typ"], rest.join(":")), "Das Zuordnen ist fehlgeschlagen.");
                }}>
                Zuordnen
              </button>
              <button type="button" className="auth-link" onClick={() => setModus("")}>Abbrechen</button>
            </div>
          )}
        </td></tr>
      )}
      {modus === "ignorieren" && (
        <tr><td colSpan={6}>
          <form
            className="bank-auswahl"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              ausfuehren(() => ignoriereUmsatz(accessToken, umsatz.id, grund.trim()), "Das Ignorieren ist fehlgeschlagen.");
            }}
          >
            <input value={grund} onChange={(e) => setGrund(e.target.value)} placeholder="Grund, z. B. Bankgebühr oder Privatentnahme" maxLength={200} required />
            <button type="submit" disabled={arbeitet || !grund.trim()}>Ignorieren</button>
            <button type="button" className="auth-link" onClick={() => setModus("")}>Abbrechen</button>
          </form>
        </td></tr>
      )}
    </>
  );
}

export function BankPage({ accessToken, onBack }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [konten, setKonten] = useState<Bankkonto[]>([]);
  const [kontoId, setKontoId] = useState("");
  const [filter, setFilter] = useState<UmsatzFilter>("offen");
  const [umsaetze, setUmsaetze] = useState<Umsatz[]>([]);
  const [zusammenfassung, setZusammenfassung] = useState<Zusammenfassung | null>(null);
  const [meldung, setMeldung] = useState("");
  const [ausgewaehlt, setAusgewaehlt] = useState<Set<string>>(new Set());
  const [bezeichnung, setBezeichnung] = useState("");
  const [iban, setIban] = useState("");
  const [legtAn, setLegtAn] = useState(false);

  const [ladeZaehler, setLadeZaehler] = useState(0);
  const neuLaden = () => setLadeZaehler((zaehler) => zaehler + 1);

  useEffect(() => {
    let aktiv = true;
    Promise.all([listKonten(accessToken), listUmsaetze(accessToken, filter), getZusammenfassung(accessToken)])
      .then(([kontenListe, liste, summe]) => {
        if (!aktiv) return;
        setKonten(kontenListe);
        setKontoId((aktuell) => aktuell || kontenListe[0]?.id || "");
        setUmsaetze(liste.umsaetze);
        setZusammenfassung(summe);
        setAusgewaehlt(new Set(liste.umsaetze.filter((u) => u.vorschlag?.sicher && u.status === "offen").map((u) => u.id)));
        setStatus("ready");
      })
      .catch((err) => {
        if (!aktiv) return;
        setError(err instanceof ApiError ? err.message : "Der Kontoauszug konnte nicht geladen werden.");
        setStatus("error");
      });
    return () => { aktiv = false; };
  }, [accessToken, filter, ladeZaehler]);

  async function legeKontoAn(event: FormEvent) {
    event.preventDefault();
    setLegtAn(true);
    setError("");
    try {
      const konto = await createKonto(accessToken, bezeichnung.trim(), iban);
      setBezeichnung("");
      setIban("");
      setKontoId(konto.id);
      neuLaden();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Das Konto konnte nicht angelegt werden.");
    } finally {
      setLegtAn(false);
    }
  }

  function nachImport(ergebnis: ImportErgebnis) {
    setMeldung(
      `${ergebnis.neu} neue ${ergebnis.neu === 1 ? "Umsatz" : "Umsätze"} importiert` +
      (ergebnis.doppelt ? `, ${ergebnis.doppelt} waren schon vorhanden.` : "."),
    );
    neuLaden();
  }

  async function bestaetigeAlleSicheren() {
    setError("");
    try {
      const ergebnis = await bestaetigeSichere(accessToken, [...ausgewaehlt]);
      setMeldung(
        `${ergebnis.bestaetigt} Zuordnung${ergebnis.bestaetigt === 1 ? "" : "en"} bestätigt` +
        (ergebnis.uebersprungen.length ? `, ${ergebnis.uebersprungen.length} übersprungen.` : "."),
      );
      neuLaden();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Die Zuordnungen konnten nicht bestätigt werden.");
    }
  }

  if (status === "loading") return <PageState label="Kontoauszug wird geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={() => { setStatus("loading"); neuLaden(); }} />;
  const konto = konten.find((k) => k.id === kontoId) ?? null;

  return (
    <div className="invoices-page">
      <PageHeader
        title="Kontoauszug"
        description="Zahlungen aus deinem Bankkonto importieren und Rechnungen und Belegen zuordnen."
        onBack={onBack}
      />

      {meldung && <p className="hinweis" role="status">{meldung}</p>}
      {error && <p className="auth-error" role="alert">{error}</p>}

      {konten.length === 0 ? (
        <form className="panel" onSubmit={legeKontoAn}>
          <h2>Bankkonto anlegen</h2>
          <p className="auth-hint">Lege zuerst das Konto an, dessen Auszüge du importieren möchtest.</p>
          <label htmlFor="bk-bezeichnung">Bezeichnung</label>
          <input id="bk-bezeichnung" value={bezeichnung} onChange={(e) => setBezeichnung(e.target.value)} placeholder="z. B. Geschäftskonto" required maxLength={100} />
          <label htmlFor="bk-iban">IBAN (optional)</label>
          <input id="bk-iban" value={iban} onChange={(e) => setIban(e.target.value)} placeholder="DE00 0000 0000 0000 0000 00" maxLength={40} />
          <button type="submit" disabled={legtAn || !bezeichnung.trim()}>{legtAn ? "Wird angelegt …" : "Konto anlegen"}</button>
        </form>
      ) : (
        <>
          {konten.length > 1 && (
            <div className="field-row">
              <div>
                <label htmlFor="bk-konto">Konto</label>
                <select id="bk-konto" value={kontoId} onChange={(e) => setKontoId(e.target.value)}>
                  {konten.map((k) => <option key={k.id} value={k.id}>{k.bezeichnung}</option>)}
                </select>
              </div>
            </div>
          )}
          {konto && <ImportPanel accessToken={accessToken} konto={konto} onImported={nachImport} />}

          <div className="pill-row" role="tablist" aria-label="Umsätze filtern">
            {FILTER.map((eintrag) => (
              <button
                key={eintrag.wert} type="button" role="tab" aria-selected={filter === eintrag.wert}
                className={`pill${filter === eintrag.wert ? " pill--aktiv" : ""}`}
                onClick={() => setFilter(eintrag.wert)}
              >
                {eintrag.label(zusammenfassung)}
              </button>
            ))}
          </div>

          {ausgewaehlt.size > 0 && filter === "offen" && (
            <div className="panel bank-sammelaktion">
              <span>
                {ausgewaehlt.size} {ausgewaehlt.size === 1 ? "Zahlung passt" : "Zahlungen passen"} sicher zu einer Rechnung
                (Betrag und Rechnungsnummer stimmen).
              </span>
              <button type="button" onClick={bestaetigeAlleSicheren}>Alle sicheren bestätigen</button>
            </div>
          )}

          {umsaetze.length === 0 ? (
            <div className="empty-state">
              <h2>{filter === "offen" ? "Keine offenen Umsätze" : "Keine Umsätze in dieser Ansicht"}</h2>
              <p className="auth-hint" style={{ margin: 0 }}>
                {filter === "offen" ? "Importiere einen Kontoauszug, um Zahlungen abzugleichen." : "Hier erscheinen Umsätze, sobald es passende gibt."}
              </p>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="positions-table">
                <thead>
                  <tr><th /><th>Datum</th><th>Gegenpartei</th><th className="number">Betrag</th><th>Zuordnung</th><th /></tr>
                </thead>
                <tbody>
                  {umsaetze.map((umsatz) => (
                    <UmsatzZeile
                      key={umsatz.id}
                      accessToken={accessToken}
                      umsatz={umsatz}
                      ausgewaehlt={ausgewaehlt.has(umsatz.id)}
                      onToggle={() => setAusgewaehlt((aktuell) => {
                        const neu = new Set(aktuell);
                        if (neu.has(umsatz.id)) neu.delete(umsatz.id); else neu.add(umsatz.id);
                        return neu;
                      })}
                      onChanged={neuLaden}
                      onError={setError}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
