import { useState } from "react";
import { passtZurSuche } from "./suchtext";

export interface ListenFilter<T> {
  id: string;
  label: string;
  passt: (eintrag: T) => boolean;
}

export interface ListenSortierung<T> {
  id: string;
  label: string;
  vergleiche: (a: T, b: T) => number;
}

/** Alles, was ListenWerkzeug zum Anzeigen und Bedienen braucht (unabhaengig vom Eintragstyp). */
export interface ListenSteuerung {
  suche: string;
  setSuche: (wert: string) => void;
  filterId: string;
  setFilterId: (id: string) => void;
  sortId: string;
  setSortId: (id: string) => void;
  filterReiter: { id: string; label: string; anzahl: number }[];
  sortOptionen: { id: string; label: string }[];
  /** true, sobald Suche oder Filter die Liste einschraenken */
  gefiltert: boolean;
  zuruecksetzen: () => void;
}

interface Optionen<T> {
  /** Text, in dem die Suche sucht (Name, Nummer, Betrag ...) */
  suchtext: (eintrag: T) => string;
  filter?: ListenFilter<T>[];
  /** Zusaetzlich zu "Standard" (Reihenfolge des Servers) */
  sortierungen?: ListenSortierung<T>[];
}

/** Suche, Filter-Reiter und Sortierung auf einer schon geladenen Liste. Die Zahl neben jedem
 * Reiter zaehlt die Treffer der aktuellen Suche, damit man sieht, was ein Klick bringt. */
export function useListenFilter<T>(eintraege: T[], optionen: Optionen<T>): ListenSteuerung & { sichtbar: T[] } {
  const [suche, setSuche] = useState("");
  const [filterId, setFilterId] = useState("alle");
  const [sortId, setSortId] = useState("standard");

  const filter = optionen.filter ?? [];
  const sortierungen = optionen.sortierungen ?? [];

  const gesucht = suche.trim() ? eintraege.filter((e) => passtZurSuche(optionen.suchtext(e), suche)) : eintraege;
  const aktiverFilter = filter.find((f) => f.id === filterId);
  const gefiltert = aktiverFilter ? gesucht.filter(aktiverFilter.passt) : gesucht;
  const aktiveSortierung = sortierungen.find((s) => s.id === sortId);
  const sichtbar = aktiveSortierung ? [...gefiltert].sort(aktiveSortierung.vergleiche) : gefiltert;

  const filterReiter = [
    { id: "alle", label: "Alle", anzahl: gesucht.length },
    ...filter.map((f) => ({ id: f.id, label: f.label, anzahl: gesucht.filter(f.passt).length })),
  ].filter((reiter) => reiter.id === "alle" || reiter.anzahl > 0 || reiter.id === filterId);

  return {
    suche, setSuche, filterId, setFilterId, sortId, setSortId,
    sichtbar,
    filterReiter,
    sortOptionen: [{ id: "standard", label: "Standard" }, ...sortierungen.map(({ id, label }) => ({ id, label }))],
    gefiltert: suche.trim() !== "" || filterId !== "alle",
    zuruecksetzen: () => { setSuche(""); setFilterId("alle"); },
  };
}
