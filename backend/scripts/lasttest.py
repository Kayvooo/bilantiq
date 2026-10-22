#!/usr/bin/env python3
"""Einfacher Lasttest fuer die Bilantiq-API (Release-Plan Phase 5, "Last").

Nur asyncio + httpx (beides bereits Backend-Abhaengigkeiten). Jeder virtuelle Nutzer registriert einen eigenen
Mandanten (ein Kontakt, ein Rechnungsentwurf) und fuehrt danach eine Schleife aus Login, Listen,
Dashboard und PDF-Erzeugung aus. Gemessen wird die Latenz pro Endpunkt (p50/p95/p99/max), Fehlerquote und Durchsatz.

SICHERHEIT
- Standardmaessig sind nur localhost/127.0.0.1/::1 als Ziel erlaubt.
- Andere Hosts nur mit --erlaube-fremden-host (gedacht fuer eine eigene Testinstanz, nie fuer eine Instanz mit
  echten Daten).
- Der Test legt Testkonten (lasttest-<lauf>-<n>@example.com) und Wegwerfdaten an. Nur gegen Wegwerf-Datenbanken laufen lassen.

Beispiel (lokale Wegwerf-Instanz):
    python scripts/lasttest.py --base-url http://127.0.0.1:8010 --nutzer 20 --dauer 30

Grenze: Ein einzelner Python-Prozess erzeugt die Last und kann bei hoher Parallelitaet selbst zum Engpass werden;
Client und Server teilen sich bei lokalen Laeufen dieselben CPU-Kerne. Ergebnisse gelten nur fuer die getestete
Umgebung, nicht fuer Produktion (siehe docs/lasttest.md).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from urllib.parse import urlparse

import httpx

LOKALE_HOSTS = {"localhost", "127.0.0.1", "::1"}
PASSWORT = "lasttest correct horse battery staple"


class Messung:
    def __init__(self) -> None:
        self.zeiten: dict[str, list[float]] = defaultdict(list)
        self.status: dict[str, Counter] = defaultdict(Counter)
        self.fehler: dict[str, int] = defaultdict(int)  # Transportfehler/Timeouts

    def erfasse(self, name: str, dauer: float, code: int | None) -> None:
        if code is None:
            self.fehler[name] += 1
            return
        self.zeiten[name].append(dauer)
        self.status[name][code] += 1

    def ok(self, name: str) -> int:
        return sum(n for c, n in self.status[name].items() if 200 <= c < 400)


def perzentil(werte: list[float], p: float) -> float:
    if not werte:
        return float("nan")
    s = sorted(werte)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return s[k]


async def anfrage(client: httpx.AsyncClient, m: Messung, name: str, methode: str, url: str, **kw) -> httpx.Response | None:
    t0 = time.perf_counter()
    try:
        r = await client.request(methode, url, **kw)
    except httpx.HTTPError:
        m.erfasse(name, time.perf_counter() - t0, None)
        return None
    m.erfasse(name, time.perf_counter() - t0, r.status_code)
    return r


async def aufbau(client: httpx.AsyncClient, m: Messung, lauf: str, n: int) -> dict | None:
    """Registrierung, ein Kontakt und ein Rechnungsentwurf pro virtuellem Nutzer (Setup, wird getrennt gemessen)."""
    email = f"lasttest-{lauf}-{n}@example.com"
    r = await anfrage(client, m, "setup_registrierung", "POST", "/auth/register",
                      json={"email": email, "password": PASSWORT, "firmenname": f"Lasttest {n} GmbH"})
    if r is None or r.status_code != 201 or not r.json().get("access_token"):
        return None
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    k = await anfrage(client, m, "setup_kontakt", "POST", "/kontakte", headers=h,
                      json={"name": "Beispiel Kunde GmbH", "strasse": "Kundenweg 2", "plz": "80331", "ort": "Muenchen",
                            "land": "DE", "ist_geschaeftskunde": True})
    if k is None or k.status_code != 201:
        return None
    heute = date.today()
    i = await anfrage(client, m, "setup_rechnung", "POST", "/invoices", headers=h, json={
        "kontakt_id": k.json()["id"], "leistungsdatum": heute.isoformat(),
        "faelligkeitsdatum": (heute + timedelta(days=14)).isoformat(), "waehrung": "EUR",
        "positionen": [
            {"beschreibung": "Beratung", "menge": "2", "einzelpreis": "500.00", "ust_satz": "19.00"},
            {"beschreibung": "Reisekosten", "menge": "1", "einzelpreis": "50.00", "ust_satz": "0.00"},
        ]})
    if i is None or i.status_code != 201:
        return None
    return {"email": email, "invoice_id": i.json()["id"], "headers": h}


async def nutzer_schleife(client: httpx.AsyncClient, m: Messung, ctx: dict, ende: float, szenarien: list[tuple[str, int]]) -> None:
    namen = [n for n, gewicht in szenarien for _ in range(gewicht)]
    i = 0
    h = ctx["headers"]
    while time.perf_counter() < ende:
        name = namen[i % len(namen)]
        i += 1
        if name == "login":
            r = await anfrage(client, m, "login", "POST", "/auth/login", json={"email": ctx["email"], "password": PASSWORT})
            if r is not None and r.status_code == 200 and r.json().get("access_token"):
                h = ctx["headers"] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        elif name == "listen":
            await anfrage(client, m, "liste_rechnungen", "GET", "/invoices", headers=h)
            await anfrage(client, m, "liste_kontakte", "GET", "/kontakte", headers=h)
        elif name == "dashboard":
            await anfrage(client, m, "dashboard", "GET", "/berichte/dashboard", headers=h)
        elif name == "pdf":
            r = await anfrage(client, m, "rechnungs_pdf", "GET", f"/invoices/{ctx['invoice_id']}/pdf", headers=h)
            if r is not None and r.status_code == 200 and not r.content.startswith(b"%PDF"):
                m.erfasse("rechnungs_pdf_ungueltig", 0.0, 500)


def parse_szenarien(text: str) -> list[tuple[str, int]]:
    ergebnis = []
    for teil in text.split(","):
        name, _, gewicht = teil.partition(":")
        name = name.strip()
        if name not in {"login", "listen", "dashboard", "pdf"}:
            raise SystemExit(f"Unbekanntes Szenario: {name} (erlaubt: login, listen, dashboard, pdf)")
        ergebnis.append((name, int(gewicht or 1)))
    return ergebnis


def pruefe_ziel(base_url: str, fremd_erlaubt: bool) -> None:
    host = (urlparse(base_url).hostname or "").lower()
    if not host:
        raise SystemExit("Ungueltige --base-url.")
    if host not in LOKALE_HOSTS and not fremd_erlaubt:
        raise SystemExit(f"Abbruch: {host} ist nicht lokal. Fuer eine eigene Testinstanz bewusst --erlaube-fremden-host setzen.")


def bericht(m: Messung, dauer: float, args, nutzer_ok: int) -> dict:
    zeilen = {}
    gesamt_anf = 0
    gesamt_fehl = 0
    for name in sorted(set(m.zeiten) | set(m.fehler)):
        z = [x * 1000 for x in m.zeiten[name]]
        n = len(z) + m.fehler[name]
        ok = m.ok(name)
        fehl = n - ok
        gesamt_anf += n
        gesamt_fehl += fehl
        zeilen[name] = {
            "anfragen": n, "erfolgreich": ok, "fehler": fehl, "transportfehler": m.fehler[name],
            "status": {str(c): k for c, k in sorted(m.status[name].items())},
            "p50_ms": round(perzentil(z, 50), 1), "p95_ms": round(perzentil(z, 95), 1),
            "p99_ms": round(perzentil(z, 99), 1), "max_ms": round(max(z), 1) if z else None,
            "mittel_ms": round(statistics.fmean(z), 1) if z else None,
        }
    return {"basis_url": args.base_url, "nutzer_angefordert": args.nutzer, "nutzer_aufgebaut": nutzer_ok,
            "laufzeit_s": round(dauer, 1), "anfragen_gesamt": gesamt_anf, "fehler_gesamt": gesamt_fehl,
            "fehlerquote": round(gesamt_fehl / gesamt_anf, 4) if gesamt_anf else None,
            "anfragen_pro_s": round(gesamt_anf / dauer, 1) if dauer else None, "endpunkte": zeilen}


def drucke(b: dict, titel: str = "Lastphase", kurz: bool = False) -> None:
    if titel == "Lastphase":
        print(f"\n== {titel} ==  Ziel: {b['basis_url']}  Nutzer: {b['nutzer_aufgebaut']}/{b['nutzer_angefordert']}  Laufzeit: {b['laufzeit_s']} s")
        print(f"Anfragen: {b['anfragen_gesamt']}  Fehler: {b['fehler_gesamt']}  Fehlerquote: {b['fehlerquote']}  Durchsatz: {b['anfragen_pro_s']} Anfragen/s")
    else:
        print(f"\n== {titel} == (Dauer pro Anfrage, Setup lief mit begrenzter Parallelitaet)")
    kopf = f"{'Endpunkt':<24}{'n':>7}{'fehler':>8}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'max ms':>10}  Status"
    print(kopf)
    print("-" * len(kopf))
    for name, z in b["endpunkte"].items():
        print(f"{name:<24}{z['anfragen']:>7}{z['fehler']:>8}{z['p50_ms']:>10}{z['p95_ms']:>10}{z['p99_ms']:>10}{str(z['max_ms']):>10}  {z['status']}")


async def haupt(args) -> int:
    pruefe_ziel(args.base_url, args.erlaube_fremden_host)
    lauf = secrets.token_hex(3)
    m = Messung()        # Lastphase
    setup_m = Messung()  # Gesundheitspruefung und Setup, bewusst getrennt ausgewertet
    limits = httpx.Limits(max_connections=max(10, args.nutzer * 2), max_keepalive_connections=max(10, args.nutzer * 2))
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout, limits=limits) as client:
        r = await anfrage(client, setup_m, "gesundheit", "GET", "/health/ready")
        if r is None or r.status_code != 200:
            print(f"Ziel nicht bereit ({'keine Antwort' if r is None else r.status_code}). Abbruch.", file=sys.stderr)
            return 3
        print(f"Setup: {args.nutzer} Nutzer registrieren (parallel, max. {args.setup_parallel}) ...")
        sem = asyncio.Semaphore(args.setup_parallel)

        async def setup(n: int):
            async with sem:
                return await aufbau(client, setup_m, lauf, n)

        kontexte = [c for c in await asyncio.gather(*(setup(n) for n in range(args.nutzer))) if c]
        if not kontexte:
            print("Kein Nutzer konnte aufgebaut werden. Abbruch.", file=sys.stderr)
            drucke(bericht(setup_m, 1.0, args, 0), titel="Setup")
            return 3
        drucke(bericht(setup_m, 1.0, args, len(kontexte)), titel="Setup", kurz=True)
        print(f"Last: {len(kontexte)} Nutzer, {args.dauer} s, Szenarien {args.szenarien} ...")
        t0 = time.perf_counter()
        ende = t0 + args.dauer
        await asyncio.gather(*(nutzer_schleife(client, m, c, ende, parse_szenarien(args.szenarien)) for c in kontexte))
        dauer = time.perf_counter() - t0
    b = bericht(m, dauer, args, len(kontexte))
    b["setup"] = bericht(setup_m, 1.0, args, len(kontexte))["endpunkte"]
    drucke(b, titel="Lastphase")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(b, f, indent=2, ensure_ascii=False)
        print(f"\nJSON geschrieben: {args.json_out}")
    nicht_ok = b["fehlerquote"] is not None and b["fehlerquote"] > args.max_fehlerquote
    return 1 if nicht_ok else 0


def main() -> None:
    p = argparse.ArgumentParser(description="Lasttest fuer die Bilantiq-API (nur Wegwerf-/Staging-Umgebungen).")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="Standard: lokale Instanz")
    p.add_argument("--nutzer", type=int, default=10, help="Anzahl virtueller Nutzer, jeder mit eigenem Mandanten")
    p.add_argument("--dauer", type=float, default=30.0, help="Dauer der Lastphase in Sekunden")
    p.add_argument("--szenarien", default="login:1,listen:3,dashboard:2,pdf:2",
                   help="Gewichtete Mischung, z. B. login:1,listen:3,dashboard:2,pdf:2")
    p.add_argument("--timeout", type=float, default=30.0, help="Timeout pro Anfrage in Sekunden")
    p.add_argument("--setup-parallel", type=int, default=5, help="gleichzeitige Registrierungen im Setup (bcrypt ist CPU-lastig)")
    p.add_argument("--max-fehlerquote", type=float, default=0.01, help="Exit 1, wenn die Fehlerquote darueber liegt")
    p.add_argument("--json-out", default=None, help="Ergebnis zusaetzlich als JSON speichern")
    p.add_argument("--erlaube-fremden-host", action="store_true", help="Nicht-lokales Ziel (eigene Testinstanz) bewusst erlauben")
    args = p.parse_args()
    if args.nutzer < 1 or args.dauer <= 0:
        raise SystemExit("--nutzer und --dauer muessen positiv sein.")
    parse_szenarien(args.szenarien)
    sys.exit(asyncio.run(haupt(args)))


if __name__ == "__main__":
    main()
