import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../auth/api";
import { AiQuoteDraftPanel } from "../ai/AiDraftPanel";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { KeineListenTreffer, ListenWerkzeug } from "../../components/ListenWerkzeug";
import { betragSuchtext } from "../../lib/suchtext";
import { useListenFilter } from "../../lib/useListenFilter";
import { useFokus } from "../../lib/useFokus";
import { KontaktForm } from "../invoices/KontaktForm";
import { listKontakte, type Kontakt } from "../invoices/api";
import { listQuotes, type Quote, type QuoteDraft } from "./api";
import { QuoteForm } from "./QuoteForm";
import { QuoteList } from "./QuoteList";
import {
  DEFAULT_BUCHHALTUNGSEINSTELLUNGEN,
  getBuchhaltungseinstellungen,
  type Buchhaltungseinstellungen,
} from "../buchhaltungseinstellungen/api";

interface Props {
  accessToken: string;
  onBack: () => void;
  /** Datensatz, zu dem die Suche gesprungen ist (wird markiert) */
  fokusId?: string;
}

export function QuotesPage({ accessToken, onBack, fokusId }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [kontakte, setKontakte] = useState<Kontakt[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [einstellungen, setEinstellungen] = useState<Buchhaltungseinstellungen>(DEFAULT_BUCHHALTUNGSEINSTELLUNGEN);
  const [showKontaktForm, setShowKontaktForm] = useState(false);
  const [aiDraft, setAiDraft] = useState<QuoteDraft | undefined>(undefined);
  const kontaktNamen = useMemo(() => new Map(kontakte.map((k) => [k.id, k.name])), [kontakte]);
  const werkzeug = useListenFilter(quotes, {
    suchtext: (q) => [q.nummer, kontaktNamen.get(q.kontakt_id), betragSuchtext(q.brutto_gesamt)].filter(Boolean).join(" "),
    filter: [
      { id: "entwurf", label: "Entwurf", passt: (q) => q.anzeige_status === "entwurf" },
      { id: "versendet", label: "Versendet", passt: (q) => q.anzeige_status === "versendet" },
      { id: "angenommen", label: "Angenommen", passt: (q) => q.anzeige_status === "angenommen" },
      { id: "abgelehnt", label: "Abgelehnt", passt: (q) => q.anzeige_status === "abgelehnt" },
      { id: "abgelaufen", label: "Abgelaufen", passt: (q) => q.anzeige_status === "abgelaufen" },
    ],
    sortierungen: [
      { id: "betrag-ab", label: "Betrag, höchster zuerst", vergleiche: (a, b) => Number(b.brutto_gesamt) - Number(a.brutto_gesamt) },
      { id: "betrag-auf", label: "Betrag, niedrigster zuerst", vergleiche: (a, b) => Number(a.brutto_gesamt) - Number(b.brutto_gesamt) },
      { id: "gueltig", label: "Gültig bis, früheste zuerst", vergleiche: (a, b) => a.gueltig_bis.localeCompare(b.gueltig_bis) },
    ],
  });

  async function reload() {
    try {
      const [k, q, e] = await Promise.all([
        listKontakte(accessToken, { typ: "kunde" }),
        listQuotes(accessToken),
        getBuchhaltungseinstellungen(accessToken),
      ]);
      setKontakte(k);
      setQuotes(q);
      setEinstellungen(e);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Daten konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  useFokus(fokusId, status === "ready" && quotes.some((q) => q.id === fokusId));

  if (status === "loading") return <PageState label="Angebote werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={reload} />;

  return (
    <div className="invoices-page">
      <PageHeader title="Angebote" description="Angebote vorbereiten, freigeben und in Rechnungen umwandeln." onBack={onBack} />

      {showKontaktForm || kontakte.length === 0 ? (
        <KontaktForm accessToken={accessToken} onCreated={() => { setShowKontaktForm(false); reload(); }} onCancel={() => setShowKontaktForm(false)} />
      ) : (
        <>
          <AiQuoteDraftPanel accessToken={accessToken} onGenerated={setAiDraft} />
          <QuoteForm
            accessToken={accessToken}
            kontakte={kontakte}
            einstellungen={einstellungen}
            initialDraft={aiDraft}
            onCreated={() => { setAiDraft(undefined); reload(); }}
            onNewKontakt={() => setShowKontaktForm(true)}
          />
        </>
      )}

      <h2 className="section-title">Alle Angebote</h2>
      {quotes.length > 0 && <ListenWerkzeug steuerung={werkzeug} placeholder="Nummer, Kunde oder Betrag" ariaLabel="Angebote durchsuchen" />}
      {quotes.length > 0 && werkzeug.sichtbar.length === 0 ? (
        <KeineListenTreffer onZuruecksetzen={werkzeug.zuruecksetzen} />
      ) : (
        <QuoteList accessToken={accessToken} quotes={werkzeug.sichtbar} onChanged={reload} />
      )}
    </div>
  );
}
