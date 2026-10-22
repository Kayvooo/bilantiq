import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { ApiError } from "../features/auth/api";
import { sucheAnfrage, type SucheErgebnis } from "../features/suche/api";
import { NAV_TREE, NAV_TREE_VERWALTEN, type DesktopStep } from "../lib/navTree";
import { normalisiere as norm } from "../lib/suchtext";
import { useIstInhaber } from "../lib/useIstInhaber";
import { SearchIcon } from "./icons";

/** Wohin ein Eintrag fuehrt. `fokusId` oeffnet den Datensatz, `aktion` startet "Neu"/"Import". */
export interface PaletteZiel {
  step: DesktopStep;
  fokusId?: string;
  aktion?: "neu" | "import";
  /** Rechnungen aus dem alten Programm liegen in einem eigenen Reiter der Rechnungsseite */
  ansicht?: "altsystem";
}

interface Props {
  accessToken: string;
  onSchliessen: () => void;
  onWaehle: (ziel: PaletteZiel) => void;
}

interface Eintrag {
  id: string;
  nr: number;
  titel: string;
  untertitel?: string | null;
  ziel: PaletteZiel;
}

interface Block {
  id: string;
  titel: string;
  eintraege: Eintrag[];
  weitere: number;
}

const ENTPRELL_MS = 250;
const MIN_ZEICHEN = 2;

const TYP_LABEL: Record<string, string> = {
  kontakte: "Kontakte", rechnungen: "Rechnungen", angebote: "Angebote", belege: "Belege", produkte: "Produkte",
};

interface Aktion {
  id: string;
  titel: string;
  hinweis: string;
  suchtext: string;
  ziel: PaletteZiel;
  nurInhaber?: boolean;
}

/** Schnellaktionen. Sie landen auf der jeweiligen Seite, ohne etwas anzulegen oder zu senden. */
const AKTIONEN: Aktion[] = [
  { id: "neue-rechnung", titel: "Neue Rechnung", hinweis: "Rechnungseditor öffnen", suchtext: "neue rechnung erstellen schreiben", ziel: { step: "invoices", aktion: "neu" } },
  { id: "beleg", titel: "Beleg hochladen", hinweis: "Foto oder PDF auslesen lassen", suchtext: "beleg hochladen scannen quittung ausgabe", ziel: { step: "receipts" } },
  { id: "kontakt", titel: "Kontakt anlegen", hinweis: "Neuer Kunde oder Lieferant", suchtext: "kontakt anlegen neu kunde lieferant", ziel: { step: "contacts", aktion: "neu" } },
  { id: "import", titel: "Daten importieren", hinweis: "Kontakte aus Excel oder altem Programm", suchtext: "daten importieren excel csv kontakte altes programm", ziel: { step: "contacts", aktion: "import" }, nurInhaber: true },
  { id: "umzug", titel: "Datenumzug", hinweis: "Von einem anderen Programm wechseln", suchtext: "datenumzug umzug wechsel altes programm anderer anbieter lexoffice sevdesk migration", ziel: { step: "umzug" } },
  { id: "kontoauszug", titel: "Kontoauszug importieren", hinweis: "Bankumsätze abgleichen", suchtext: "kontoauszug importieren bank umsaetze abgleich", ziel: { step: "bank" } },
];

interface Seite { id: string; titel: string; ueber?: string; suchtext: string; ziel: PaletteZiel }

function baueSeiten(): Seite[] {
  const gesehen = new Set<DesktopStep>();
  const seiten: Seite[] = [];
  for (const punkt of [...NAV_TREE, ...NAV_TREE_VERWALTEN]) {
    if (punkt.step && !gesehen.has(punkt.step)) {
      gesehen.add(punkt.step);
      seiten.push({ id: `seite-${punkt.step}`, titel: punkt.label, suchtext: norm(punkt.label), ziel: { step: punkt.step } });
    }
    for (const kind of punkt.children ?? []) {
      if (!kind.step || gesehen.has(kind.step)) continue;
      gesehen.add(kind.step);
      seiten.push({ id: `seite-${kind.step}`, titel: kind.label, ueber: punkt.label, suchtext: norm(`${kind.label} ${punkt.label}`), ziel: { step: kind.step } });
    }
  }
  return seiten;
}

const SEITEN = baueSeiten();

function passt(suchtext: string, tokens: string[]): boolean {
  const heuhaufen = norm(suchtext);
  return tokens.every((token) => heuhaufen.includes(token));
}

export function Befehlspalette({ accessToken, onSchliessen, onWaehle }: Props) {
  const basisId = useId();
  const listenId = `${basisId}-liste`;
  const eingabeRef = useRef<HTMLInputElement>(null);
  const schliessenRef = useRef<HTMLButtonElement>(null);
  const [anfrage, setAnfrage] = useState("");
  const [antwort, setAntwort] = useState<{ q: string; ergebnis: SucheErgebnis | null; fehler: string } | null>(null);
  const [aktiv, setAktiv] = useState(0);
  const istInhaber = useIstInhaber(accessToken);

  // Fokus in die Eingabe, danach zurueck dorthin, wo der Nutzer war; Seite dahinter nicht scrollen.
  useEffect(() => {
    const vorher = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflowVorher = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    eingabeRef.current?.focus();
    return () => {
      document.body.style.overflow = overflowVorher;
      if (vorher?.isConnected) vorher.focus();
    };
  }, []);

  const bereinigt = anfrage.trim();
  const sucheAktiv = bereinigt.length >= MIN_ZEICHEN;
  // Treffer einer älteren Eingabe werden nie angezeigt, sonst könnte Enter einen veralteten Datensatz öffnen.
  const antwortPasst = antwort?.q === bereinigt;
  const ergebnis = sucheAktiv && antwortPasst ? antwort?.ergebnis ?? null : null;
  const laedt = sucheAktiv && !antwortPasst;
  const fehler = sucheAktiv && antwortPasst ? antwort.fehler : "";

  // Serversuche: entprellt, alte Anfragen werden abgebrochen, damit keine veraltete Antwort gewinnt.
  useEffect(() => {
    if (bereinigt.length < MIN_ZEICHEN) return;
    const steuerung = new AbortController();
    const timer = window.setTimeout(() => {
      sucheAnfrage(accessToken, bereinigt, steuerung.signal)
        .then((erg) => { if (steuerung.signal.aborted) return; setAntwort({ q: bereinigt, ergebnis: erg, fehler: "" }); setAktiv(0); })
        .catch((err) => {
          if (steuerung.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
          setAntwort({ q: bereinigt, ergebnis: null, fehler: err instanceof ApiError ? err.message : "Die Suche ist fehlgeschlagen." });
        });
    }, ENTPRELL_MS);
    return () => { window.clearTimeout(timer); steuerung.abort(); };
  }, [accessToken, bereinigt]);

  const bloecke = useMemo<Block[]>(() => {
    const tokens = norm(bereinigt).split(/\s+/).filter(Boolean);
    let zaehler = 0;
    const nummeriere = (id: string, titel: string, untertitel: string | null | undefined, ziel: PaletteZiel): Eintrag => (
      { id, nr: zaehler++, titel, untertitel, ziel }
    );
    const liste: Block[] = [];

    // Treffer im Titel stehen vor Treffern nur im Stichwort ("umzug" findet zuerst "Datenumzug").
    const imTitel = (a: Aktion) => (tokens.length > 0 && passt(a.titel, tokens) ? 0 : 1);
    const aktionen = AKTIONEN
      .filter((a) => (!a.nurInhaber || istInhaber) && (tokens.length === 0 || passt(`${a.titel} ${a.suchtext}`, tokens)))
      .sort((a, b) => imTitel(a) - imTitel(b));
    if (aktionen.length) {
      liste.push({ id: "aktionen", titel: "Schnellaktionen", weitere: 0, eintraege: aktionen.map((a) => nummeriere(`aktion-${a.id}`, a.titel, a.hinweis, a.ziel)) });
    }
    for (const gruppe of ergebnis?.gruppen ?? []) {
      liste.push({
        id: gruppe.typ, titel: gruppe.label, weitere: Math.max(0, gruppe.gesamt - gruppe.treffer.length),
        eintraege: gruppe.treffer.map((t) => nummeriere(
          `${gruppe.typ}-${t.id}`, t.titel, t.untertitel,
          { step: t.ziel as DesktopStep, fokusId: t.id, ansicht: gruppe.typ === "altrechnungen" ? "altsystem" : undefined },
        )),
      });
    }
    const seiten = tokens.length ? SEITEN.filter((s) => passt(s.suchtext, tokens)).slice(0, 5) : [];
    if (seiten.length) {
      liste.push({ id: "seiten", titel: "Seiten", weitere: 0, eintraege: seiten.map((s) => nummeriere(s.id, s.titel, s.ueber, s.ziel)) });
    }
    return liste;
  }, [bereinigt, ergebnis, istInhaber]);

  const flach = useMemo(() => bloecke.flatMap((b) => b.eintraege), [bloecke]);

  useEffect(() => {
    document.getElementById(`${basisId}-opt-${aktiv}`)?.scrollIntoView({ block: "nearest" });
  }, [aktiv, basisId]);

  function bewege(richtung: 1 | -1) {
    if (flach.length === 0) return;
    setAktiv((nr) => (nr + richtung + flach.length) % flach.length);
  }

  function beiTaste(ereignis: ReactKeyboardEvent) {
    // Auf dem Schließen-Button gehören Enter und Pfeiltasten dem Button, nicht der Trefferliste.
    const imSuchfeld = ereignis.target === eingabeRef.current;
    if (!imSuchfeld && ereignis.key !== "Tab" && ereignis.key !== "Escape") return;
    switch (ereignis.key) {
      case "ArrowDown": ereignis.preventDefault(); bewege(1); break;
      case "ArrowUp": ereignis.preventDefault(); bewege(-1); break;
      case "Enter":
        if (ereignis.nativeEvent.isComposing) return;
        ereignis.preventDefault();
        if (flach[aktiv]) onWaehle(flach[aktiv].ziel);
        break;
      case "Escape": ereignis.preventDefault(); onSchliessen(); break;
      case "Tab": {
        // Fokusfalle über zwei Elemente: Suchfeld und Schließen-Button.
        const amAnfang = ereignis.target === eingabeRef.current;
        const amEnde = ereignis.target === schliessenRef.current;
        if (ereignis.shiftKey && amAnfang) { ereignis.preventDefault(); schliessenRef.current?.focus(); }
        else if (!ereignis.shiftKey && amEnde) { ereignis.preventDefault(); eingabeRef.current?.focus(); }
        break;
      }
    }
  }

  const statusText = laedt ? "Suche läuft" : fehler ? "" : sucheAktiv ? (ergebnis && ergebnis.gruppen.length ? `${flach.length} Ergebnisse` : "Keine Datensätze gefunden") : "";
  const nichtsGefunden = sucheAktiv && !laedt && !fehler && flach.length === 0;

  return (
    <div className="palette-overlay" onMouseDown={(ereignis) => { if (ereignis.target === ereignis.currentTarget) onSchliessen(); }}>
      <div className={`palette${laedt ? " palette--laedt" : ""}`} role="dialog" aria-modal="true" aria-label="Suche und Schnellaktionen" onKeyDown={beiTaste}>
        <div className="palette-eingabe">
          <SearchIcon width={20} height={20} aria-hidden="true" />
          <input
            ref={eingabeRef} type="text" role="combobox" aria-expanded="true" aria-controls={listenId} aria-autocomplete="list"
            aria-activedescendant={flach.length ? `${basisId}-opt-${aktiv}` : undefined}
            aria-label="Suchen" placeholder="Kunden, Rechnungen, Belege oder Seiten suchen …"
            autoComplete="off" autoCorrect="off" spellCheck={false} maxLength={100}
            value={anfrage} onChange={(ereignis) => { setAnfrage(ereignis.target.value); setAktiv(0); }}
          />
          <button ref={schliessenRef} type="button" className="palette-schliessen" onClick={onSchliessen} aria-label="Suche schließen">Esc</button>
        </div>

        <div className="sr-only" role="status" aria-live="polite">{statusText}</div>

        <ul id={listenId} className="palette-liste" role="listbox" aria-label="Ergebnisse" aria-busy={laedt} onMouseDown={(ereignis) => ereignis.preventDefault()}>
          {bloecke.map((block) => (
            <li key={block.id} role="presentation" className="palette-block">
              <div id={`${basisId}-${block.id}`} className="palette-gruppe" role="presentation">{block.titel}</div>
              <ul role="group" aria-labelledby={`${basisId}-${block.id}`} className="palette-gruppenliste">
                {block.eintraege.map((eintrag) => (
                  <li
                    key={eintrag.id} id={`${basisId}-opt-${eintrag.nr}`} role="option" aria-selected={eintrag.nr === aktiv}
                    className={`palette-eintrag${eintrag.nr === aktiv ? " palette-eintrag--aktiv" : ""}`}
                    onMouseMove={() => { if (aktiv !== eintrag.nr) setAktiv(eintrag.nr); }}
                    onClick={() => onWaehle(eintrag.ziel)}
                  >
                    <span className="palette-titel">{eintrag.titel}</span>
                    {eintrag.untertitel && <span className="palette-untertitel">{eintrag.untertitel}</span>}
                  </li>
                ))}
                {block.weitere > 0 && (
                  <li role="presentation" className="palette-weitere">
                    {block.weitere === 1 ? "+ 1 weiterer Treffer" : `+ ${block.weitere} weitere Treffer`}. Fasse den Suchbegriff genauer.
                  </li>
                )}
              </ul>
            </li>
          ))}
        </ul>

        {fehler && <p className="auth-error palette-meldung" role="alert">{fehler}</p>}
        {laedt && flach.length === 0 && !fehler && <p className="palette-meldung palette-hinweis">Suche läuft …</p>}
        {nichtsGefunden && <p className="palette-meldung palette-hinweis">Nichts gefunden für „{bereinigt}“.</p>}
        {!sucheAktiv && bereinigt.length > 0 && <p className="palette-meldung palette-hinweis">Tippe mindestens {MIN_ZEICHEN} Zeichen, um Datensätze zu durchsuchen.</p>}
        {ergebnis && ergebnis.unvollstaendig.length > 0 && (
          <p className="palette-meldung palette-warnung" role="status">
            Nicht alle Daten durchsucht ({ergebnis.unvollstaendig.map((typ) => TYP_LABEL[typ] ?? typ).join(", ")}). Fasse den Suchbegriff genauer, um ältere Einträge zu finden.
          </p>
        )}

        <div className="palette-fuss" aria-hidden="true">
          <span><kbd>↑</kbd> <kbd>↓</kbd> wählen</span>
          <span><kbd>Enter</kbd> öffnen</span>
          <span><kbd>Esc</kbd> schließen</span>
        </div>
      </div>
    </div>
  );
}
