import { useEffect, useRef, useState } from "react";
import { ApiError } from "../auth/api";
import { AiInvoiceDraftPanel } from "../ai/AiDraftPanel";
import { ComplianceHinweis } from "../../components/ComplianceHinweis";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { KeineListenTreffer, ListenWerkzeug } from "../../components/ListenWerkzeug";
import { betragSuchtext } from "../../lib/suchtext";
import { useIstInhaber } from "../../lib/useIstInhaber";
import { useListenFilter } from "../../lib/useListenFilter";
import { useFokus } from "../../lib/useFokus";
import { listInvoices, listKontakte, type Invoice, type InvoiceDraft, type Kontakt } from "./api";
import { AltsystemRechnungen } from "../altrechnungen/AltsystemRechnungen";
import { listeAltrechnungen } from "../altrechnungen/api";
import { InvoiceEditor } from "./InvoiceEditor";
import { InvoiceList } from "./InvoiceList";
import { KontaktForm } from "./KontaktForm";
import {
  DEFAULT_BUCHHALTUNGSEINSTELLUNGEN,
  getBuchhaltungseinstellungen,
  type Buchhaltungseinstellungen,
} from "../buchhaltungseinstellungen/api";

interface Props {
  accessToken: string;
  onBack: () => void;
  startInEditor?: boolean;
  initialTab?: "inhalt" | "design";
  /** Rechnung, zu der die Suche gesprungen ist (wird markiert) */
  fokusId?: string;
  /** Schnellaktion "Neue Rechnung" aus der Befehlspalette */
  startMitNeu?: boolean;
  /** Sprung zu einer Rechnung aus dem alten Programm */
  startAnsicht?: "altsystem";
}

export function InvoicesPage({ accessToken, onBack, startInEditor, initialTab, fokusId, startMitNeu, startAnsicht }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [kontakte, setKontakte] = useState<Kontakt[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [einstellungen, setEinstellungen] = useState<Buchhaltungseinstellungen>(DEFAULT_BUCHHALTUNGSEINSTELLUNGEN);
  const [showKontaktForm, setShowKontaktForm] = useState(false);
  const [showEditor, setShowEditor] = useState(startInEditor ?? false);
  const [aiDraft, setAiDraft] = useState<InvoiceDraft | undefined>(undefined);
  const [ansicht, setAnsicht] = useState<"bilantiq" | "altsystem">(startAnsicht === "altsystem" ? "altsystem" : "bilantiq");
  const [altAnzahl, setAltAnzahl] = useState(0);
  const istInhaber = useIstInhaber(accessToken);
  const werkzeug = useListenFilter(invoices, {
    suchtext: (i) => [i.nummer, i.kontakt_name, i.betreff, i.referenznummer, betragSuchtext(i.brutto_gesamt)].filter(Boolean).join(" "),
    filter: [
      { id: "entwurf", label: "Entwurf", passt: (i) => i.anzeige_status === "entwurf" },
      { id: "final", label: "Offen", passt: (i) => i.anzeige_status === "final" },
      { id: "ueberfaellig", label: "Überfällig", passt: (i) => i.anzeige_status === "ueberfaellig" },
      { id: "bezahlt", label: "Bezahlt", passt: (i) => i.anzeige_status === "bezahlt" },
      { id: "storniert", label: "Storniert", passt: (i) => i.anzeige_status === "storniert" },
    ],
    sortierungen: [
      { id: "betrag-ab", label: "Betrag, höchster zuerst", vergleiche: (a, b) => Number(b.brutto_gesamt) - Number(a.brutto_gesamt) },
      { id: "betrag-auf", label: "Betrag, niedrigster zuerst", vergleiche: (a, b) => Number(a.brutto_gesamt) - Number(b.brutto_gesamt) },
      { id: "faellig", label: "Fälligkeit, früheste zuerst", vergleiche: (a, b) => a.faelligkeitsdatum.localeCompare(b.faelligkeitsdatum) },
      { id: "kunde", label: "Kunde A–Z", vergleiche: (a, b) => a.kontakt_name.localeCompare(b.kontakt_name, "de") },
    ],
  });

  async function reload() {
    try {
      const [k, i, e, alt] = await Promise.all([
        listKontakte(accessToken),
        listInvoices(accessToken),
        getBuchhaltungseinstellungen(accessToken),
        // Der Reiter fuer Rechnungen aus dem alten Programm ist Beiwerk: Fehler hier sollen die Seite nicht kippen.
        listeAltrechnungen(accessToken, { limit: 1 }).then((antwort) => antwort.gesamt).catch(() => 0),
      ]);
      setAltAnzahl(alt);
      setKontakte(k);
      setInvoices(i);
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

  // "Neue Rechnung" aus der Befehlspalette: Editor oeffnen, sobald Kontakte da sind (ohne Kontakt
  // zeigt die Seite ohnehin zuerst das Kontaktformular).
  const neuGestartet = useRef(false);
  useEffect(() => {
    if (!startMitNeu || status !== "ready" || neuGestartet.current) return;
    neuGestartet.current = true;
    if (kontakte.length > 0) setShowEditor(true);
  }, [startMitNeu, status, kontakte.length]);
  useFokus(fokusId, status === "ready" && !showEditor && ansicht === "bilantiq" && invoices.some((i) => i.id === fokusId));

  if (status === "loading") {
    return <PageState label="Rechnungen werden geladen …" />;
  }

  if (status === "error") {
    return <PageState label={error} error onRetry={reload} />;
  }

  if (showEditor) {
    return (
      <InvoiceEditor
        accessToken={accessToken}
        kontakte={kontakte}
        einstellungen={einstellungen}
        initialTab={initialTab}
        onBack={startInEditor ? onBack : () => { setShowEditor(false); setAiDraft(undefined); }}
        onNewKontakt={() => setShowKontaktForm(true)}
        initialDraft={aiDraft}
        onCreated={() => { setShowEditor(false); setAiDraft(undefined); reload(); }}
      />
    );
  }

  return (
    <div className="invoices-page">
      <PageHeader title="Rechnungen" description="Entwürfe, offene Beträge und Zahlungen im Blick behalten." onBack={onBack} />

      {(altAnzahl > 0 || istInhaber) && (
        <div className="pill-row" role="tablist" aria-label="Rechnungen">
          <button type="button" role="tab" aria-selected={ansicht === "bilantiq"} className={`pill${ansicht === "bilantiq" ? " pill--aktiv" : ""}`} onClick={() => setAnsicht("bilantiq")}>
            Aus Bilantiq
          </button>
          <button type="button" role="tab" aria-selected={ansicht === "altsystem"} className={`pill${ansicht === "altsystem" ? " pill--aktiv" : ""}`} onClick={() => setAnsicht("altsystem")}>
            Aus dem alten Programm{altAnzahl > 0 ? ` (${altAnzahl})` : ""}
          </button>
        </div>
      )}

      {ansicht === "altsystem" ? (
        <AltsystemRechnungen accessToken={accessToken} istInhaber={istInhaber} fokusId={fokusId} />
      ) : (
        <>
        {showKontaktForm || kontakte.length === 0 ? (
          <KontaktForm
            accessToken={accessToken}
            onCreated={() => { setShowKontaktForm(false); reload(); setShowEditor(true); }}
            onCancel={() => setShowKontaktForm(false)}
          />
        ) : (
          <div className="invoice-actions">
            <button type="button" onClick={() => { setAiDraft(undefined); setShowEditor(true); }}>+ Neue Rechnung</button>
            <AiInvoiceDraftPanel
              accessToken={accessToken}
              onGenerated={(draft) => { setAiDraft(draft); setShowEditor(true); }}
            />
          </div>
        )}

        <h2 className="section-title">Alle Rechnungen</h2>
        <ComplianceHinweis titel="E-Rechnung: Format nicht zertifiziert">
          Die erzeugten XRechnung-/ZUGFeRD-Dateien folgen EN 16931, sind aber nicht KoSIT-validiert
          bzw. Factur-X-zertifiziert. Vor dem ersten Versand an eine Behörde oder einen B2B-Kunden
          einmal mit deren System gegenprüfen.
        </ComplianceHinweis>
        {invoices.length > 0 && <ListenWerkzeug steuerung={werkzeug} placeholder="Nummer, Kunde oder Betrag" ariaLabel="Rechnungen durchsuchen" />}
        {invoices.length > 0 && werkzeug.sichtbar.length === 0 ? (
          <KeineListenTreffer onZuruecksetzen={werkzeug.zuruecksetzen} />
        ) : (
          <InvoiceList accessToken={accessToken} invoices={werkzeug.sichtbar} onChanged={reload} />
        )}
        </>
      )}
    </div>
  );
}
