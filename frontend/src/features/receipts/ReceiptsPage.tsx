import { useEffect, useState } from "react";
import { ApiError } from "../auth/api";
import { PageHeader } from "../../components/PageHeader";
import { PageState } from "../../components/PageState";
import { KeineListenTreffer, ListenWerkzeug } from "../../components/ListenWerkzeug";
import { betragSuchtext } from "../../lib/suchtext";
import { useListenFilter } from "../../lib/useListenFilter";
import { useFokus } from "../../lib/useFokus";
import { listBelege, type Receipt } from "./api";
import { ReceiptList } from "./ReceiptList";
import { ReceiptUpload } from "./ReceiptUpload";

interface Props {
  accessToken: string;
  onBack: () => void;
  /** Datensatz, zu dem die Suche gesprungen ist (wird markiert) */
  fokusId?: string;
}

export function ReceiptsPage({ accessToken, onBack, fokusId }: Props) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [belege, setBelege] = useState<Receipt[]>([]);
  const betrag = (b: Receipt) => Number(b.betrag.wert) || 0;
  const werkzeug = useListenFilter(belege, {
    suchtext: (b) => [b.anbieter.wert, b.rechnungsnummer, b.kategorie_vorschlag.wert, betragSuchtext(b.betrag.wert)].filter(Boolean).join(" "),
    filter: [
      { id: "neu", label: "Neu", passt: (b) => b.status === "neu" },
      { id: "unklar", label: "Prüfung nötig", passt: (b) => b.status === "unklar" },
      { id: "geprueft", label: "Geprüft", passt: (b) => b.status === "geprueft" },
      { id: "gebucht", label: "Gebucht", passt: (b) => b.status === "gebucht" },
    ],
    sortierungen: [
      { id: "betrag-ab", label: "Betrag, höchster zuerst", vergleiche: (a, b) => betrag(b) - betrag(a) },
      { id: "betrag-auf", label: "Betrag, niedrigster zuerst", vergleiche: (a, b) => betrag(a) - betrag(b) },
      { id: "anbieter", label: "Anbieter A–Z", vergleiche: (a, b) => (a.anbieter.wert ?? "").localeCompare(b.anbieter.wert ?? "", "de") },
    ],
  });

  async function reload() {
    try {
      setBelege(await listBelege(accessToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Belege konnten nicht geladen werden.");
      setStatus("error");
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  useFokus(fokusId, status === "ready" && belege.some((b) => b.id === fokusId));

  if (status === "loading") return <PageState label="Belege werden geladen …" />;
  if (status === "error") return <PageState label={error} error onRetry={reload} />;

  return (
    <div className="invoices-page">
      <PageHeader title="Belege" description="Belege lokal auslesen, prüfen und sicher buchen." onBack={onBack} />

      <ReceiptUpload accessToken={accessToken} onUploaded={reload} />

      <h2 className="section-title">Alle Belege</h2>
      {belege.length > 0 && <ListenWerkzeug steuerung={werkzeug} placeholder="Anbieter, Betrag oder Kategorie" ariaLabel="Belege durchsuchen" />}
      {belege.length > 0 && werkzeug.sichtbar.length === 0 ? (
        <KeineListenTreffer onZuruecksetzen={werkzeug.zuruecksetzen} />
      ) : (
        <ReceiptList accessToken={accessToken} belege={werkzeug.sichtbar} onChanged={reload} />
      )}
    </div>
  );
}
