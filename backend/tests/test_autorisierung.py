"""Autorisierungs-Sweep (Release-Plan 4.4): Jede Route der FastAPI-App wird aus der laufenden App aufgelistet und geprueft.

Was hier bewusst "festgenagelt" wird (neue Routen muessen die Listen unten bewusst erweitern, siehe docs/autorisierungs-matrix.md):

- Oeffentliche Routen (ohne Anmeldung) sind genau die in ``OEFFENTLICH``.
- Alle anderen Routen antworten ohne Token mit 401, mit Pre-MFA-Token (statt voller Sitzung) mit 403.
- Die Owner-only-Routen sind genau die in ``OWNER_ONLY``; ein Mitglied bekommt dort 403.
- Es gibt keine Tarif-Gates: Die frueher gesperrten Lese-Routen in ``FRUEHER_GESPERRT`` stehen jedem Mandanten offen.
"""
import re
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from tests.test_benutzerverwaltung import _register_and_verify
from tests.test_invoices import _onboarded_mandant

OEFFENTLICH = {
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/passwort/vergessen"),  # antwortet immer gleich; IP- und Konto-Limit
    ("POST", "/auth/passwort/zuruecksetzen"),  # Einmal-Token aus der E-Mail statt Anmeldung
    ("GET", "/health"),
    ("GET", "/health/ready"),  # DB-Check fuer Monitoring, ohne Details
}
PRE_MFA = {
    ("POST", "/auth/login/mfa"),
    ("POST", "/auth/login/mfa/wiederherstellungscode"),
    ("POST", "/auth/mfa/setup"),
    ("POST", "/auth/mfa/verify"),
}
OWNER_ONLY = {
    ("GET", "/auth/datenexport"),
    ("GET", "/auth/einladungen"),
    ("POST", "/auth/einladungen"),
    ("POST", "/auth/einladungen/{einladung_id}/widerrufen"),
    ("POST", "/auth/mitglieder"),
    ("POST", "/auth/mitglieder/{user_id}/entfernen"),
    ("PUT", "/einstellungen/nummernkreis"),
    ("GET", "/stammdaten/importe"),
    ("POST", "/stammdaten/importe/{import_id}/rueckgaengig"),
    ("GET", "/stammdaten/{ziel}/export"),
    ("POST", "/stammdaten/{ziel}/import"),
    ("POST", "/stammdaten/{ziel}/import/fehlerliste"),
    ("POST", "/stammdaten/{ziel}/import/pruefen"),
    ("POST", "/stammdaten/{ziel}/import/vorschau"),
    ("GET", "/stammdaten/{ziel}/vorlage"),
    # Lohn: komplett Owner-only (Gehaltsdaten Dritter)
    ("GET", "/lohn/mitarbeitende"),
    ("POST", "/lohn/mitarbeitende"),
    ("PATCH", "/lohn/mitarbeitende/{mitarbeiter_id}"),
    ("POST", "/lohn/mitarbeitende/{mitarbeiter_id}/deaktivieren"),
    ("POST", "/lohn/mitarbeitende/{mitarbeiter_id}/reaktivieren"),
    ("GET", "/lohn/monate/{jahr}/{monat}/export"),
    ("GET", "/lohn/monatsentwuerfe"),
    ("POST", "/lohn/monatsentwuerfe"),
    ("PATCH", "/lohn/monatsentwuerfe/{entwurf_id}"),
    ("POST", "/lohn/monatsentwuerfe/{entwurf_id}/abschliessen"),
    ("GET", "/lohn/monatsentwuerfe/{entwurf_id}/lohnzettel"),
    ("POST", "/lohn/monatsentwuerfe/{entwurf_id}/reaktivieren"),
}
# Lese-Routen, die frueher Tarif-Gates hatten. Seit dem Wegfall der Tarife stehen sie allen Mandanten offen.
FRUEHER_GESPERRT = [
    ("GET", "/bank/konten"), ("GET", "/bank/umsaetze"), ("GET", "/bank/zusammenfassung"),
    ("GET", "/mahnungen"), ("GET", "/auftragsbestaetigungen"), ("GET", "/lieferscheine"),
    ("GET", "/wiederkehrende-rechnungen"), ("GET", "/berichte/bwa"), ("GET", "/berichte/susa"),
    ("GET", "/berichte/datev-export"), ("GET", "/anlagen"), ("GET", "/berichte/cashflow"),
    ("GET", "/lohn/mitarbeitende"), ("GET", "/belege/vorschlag?anbieter=x"),
]


def _routen() -> list[tuple[str, str, APIRoute]]:
    def laufe(routen):
        for r in routen:
            if type(r).__name__ == "_IncludedRouter":
                yield from laufe(r.original_router.routes)
            elif isinstance(r, APIRoute):
                yield r

    return [(m, r.path, r) for r in laufe(app.routes) for m in sorted(r.methods - {"HEAD", "OPTIONS"})]


def _namen_der_abhaengigkeiten(route: APIRoute) -> set[str]:
    gefunden: set[str] = set()

    def laufe(dep):
        for unter in dep.dependencies:
            gefunden.add(getattr(unter.call, "__name__", ""))
            laufe(unter)

    laufe(route.dependant)
    return gefunden


def _url(pfad: str) -> str:
    return re.sub(r"{(\w+)}", lambda m: "1" if m.group(1) in {"jahr", "monat"} else "x" * 36 if m.group(1) != "ziel" else "kontakte", pfad)


def test_oeffentliche_und_geschuetzte_routen_entsprechen_der_festgelegten_liste():
    oeffentlich, pre_mfa, owner = set(), set(), set()
    for methode, pfad, route in _routen():
        namen = _namen_der_abhaengigkeiten(route)
        if "require_owner" in namen:
            owner.add((methode, pfad))
        elif "require_full_auth" in namen:
            continue
        elif "require_pre_mfa" in namen:
            pre_mfa.add((methode, pfad))
        else:
            oeffentlich.add((methode, pfad))
    assert oeffentlich == OEFFENTLICH, f"Unerwartet oeffentliche (oder fehlende) Routen: {oeffentlich ^ OEFFENTLICH}"
    assert pre_mfa == PRE_MFA, pre_mfa ^ PRE_MFA
    assert owner == OWNER_ONLY, f"Owner-only-Routen weichen ab: {owner ^ OWNER_ONLY}"


def test_ohne_token_antwortet_jede_geschuetzte_route_mit_401(client: TestClient):
    geprueft = 0
    for methode, pfad, _ in _routen():
        if (methode, pfad) in OEFFENTLICH:
            continue
        antwort = client.request(methode, _url(pfad))
        assert antwort.status_code == 401, f"{methode} {pfad}: {antwort.status_code} statt 401 ohne Token"
        geprueft += 1
    assert geprueft >= 150


def test_mit_pre_mfa_token_oder_unsinnigem_token_kommt_man_nicht_an_geschuetzte_routen(client: TestClient):
    reg = client.post(
        "/auth/register", json={"email": "pre@example.com", "password": "correct horse battery staple", "firmenname": "Pre GmbH"},
    ).json()
    pre = {"Authorization": f"Bearer {reg['pre_auth_token']}"}
    voll = {"Authorization": f"Bearer {reg['access_token']}"}
    kaputt = {"Authorization": "Bearer abc.def.ghi"}
    for methode, pfad, _ in _routen():
        if (methode, pfad) in OEFFENTLICH:
            continue
        if (methode, pfad) in PRE_MFA:
            assert client.request(methode, _url(pfad), headers=voll).status_code == 403, f"{methode} {pfad} nimmt volles Token als Pre-MFA"
            continue
        assert client.request(methode, _url(pfad), headers=pre).status_code == 403, f"{methode} {pfad} akzeptiert Pre-MFA-Token"
        assert client.request(methode, _url(pfad), headers=kaputt).status_code == 401, f"{methode} {pfad} akzeptiert kaputtes Token"


@pytest.fixture
def owner_und_mitglied(client: TestClient):
    owner = _onboarded_mandant(client, email="owner-az@example.com")
    code = client.post("/auth/einladungen", headers=owner, json={}).json()["code"]
    mitglied = _register_and_verify(client, "mitglied-az@example.com", einladungscode=code)
    assert client.get("/auth/me", headers=mitglied).json()["rolle"] == "mitglied"
    return owner, mitglied


def test_mitglied_bekommt_auf_jeder_owner_only_route_403(client: TestClient, owner_und_mitglied):
    _, mitglied = owner_und_mitglied
    for methode, pfad in sorted(OWNER_ONLY):
        antwort = client.request(methode, _url(pfad), headers=mitglied, json={} if methode in {"POST", "PUT", "PATCH"} else None)
        assert antwort.status_code == 403, f"{methode} {pfad}: Mitglied bekommt {antwort.status_code}"


def test_owner_kommt_auf_den_owner_only_routen_durch_die_rollenpruefung(client: TestClient, owner_und_mitglied):
    owner, _ = owner_und_mitglied
    for methode, pfad in sorted(OWNER_ONLY):
        antwort = client.request(methode, _url(pfad), headers=owner, json={} if methode in {"POST", "PUT", "PATCH"} else None)
        assert antwort.status_code != 403, f"{methode} {pfad}: Owner bekommt 403"


def test_lohndaten_sind_fuer_mitglieder_nicht_lesbar(client: TestClient, owner_und_mitglied):
    owner, mitglied = owner_und_mitglied
    client.post("/lohn/mitarbeitende", headers=owner, json={
        "personalnummer": "P-1", "vorname": "Mara", "nachname": "Muster", "eintrittsdatum": "2026-01-15",
        "austrittsdatum": None, "monatsbrutto": "3200.00",
    })
    assert client.get("/lohn/mitarbeitende", headers=owner).status_code == 200
    assert client.get("/lohn/mitarbeitende", headers=mitglied).status_code == 403
    assert "Mara" not in client.get("/lohn/mitarbeitende", headers=mitglied).text


def test_mitglied_darf_keine_firmen_und_bankdaten_aendern_aber_das_design(client: TestClient, owner_und_mitglied):
    owner, mitglied = owner_und_mitglied
    assert client.patch("/auth/mandant", headers=owner, json={"iban": "DE89370400440532013000", "firmenname": "Echte GmbH"}).status_code == 200

    # Umleiten der Zahlungen (IBAN) oder Firmenname/Adresse/Steuernummer: nur Owner.
    for aenderung in ({"iban": "DE00000000000000000000"}, {"firmenname": "Gefaelscht GmbH"}, {"ust_id": "DE999999999"}, {"adresse": "x"}):
        assert client.patch("/auth/mandant", headers=mitglied, json=aenderung).status_code == 403, aenderung
    mandant = client.get("/auth/mandant", headers=owner).json()
    assert (mandant["iban"], mandant["firmenname"]) == ("DE89370400440532013000", "Echte GmbH")

    # Das Design-Formular schickt IBAN/BIC unveraendert mit -> keine Aenderung, darf durch.
    antwort = client.patch("/auth/mandant", headers=mitglied, json={"iban": "DE89370400440532013000", "akzentfarbe": "#112233"})
    assert antwort.status_code == 200 and antwort.json()["akzentfarbe"] == "#112233"


def test_entfernter_nutzer_verliert_sofort_den_zugriff(client: TestClient, owner_und_mitglied):
    owner, mitglied = owner_und_mitglied
    mitglieder = client.get("/auth/mitglieder", headers=owner).json()
    user_id = next(m["user_id"] for m in mitglieder if m["rolle"] == "mitglied")
    assert client.get("/kontakte", headers=mitglied).status_code == 200
    assert client.post(f"/auth/mitglieder/{user_id}/entfernen", headers=owner).status_code == 204
    assert client.get("/kontakte", headers=mitglied).status_code == 401


def test_keine_route_antwortet_mit_402_alle_funktionen_sind_frei(client: TestClient):
    headers = _onboarded_mandant(client, email="frei-az@example.com")
    for methode, pfad in FRUEHER_GESPERRT:
        status_code = client.request(methode, pfad, headers=headers).status_code
        assert status_code == 200, f"{methode} {pfad}: {status_code} statt 200"


def test_design_einstellungen_stehen_jedem_mandanten_offen(client: TestClient):
    headers = _onboarded_mandant(client, email="design-az@example.com")
    for aenderung in ({"rechnungsvorlage": "stempel"}, {"akzentfarbe": "#112233"}, {"zeige_girocode": True}, {"sprache": "en"}):
        assert client.patch("/auth/mandant", headers=headers, json=aenderung).status_code == 200, aenderung


def test_rechnungen_haben_kein_monatslimit_und_einladungen_kein_nutzerlimit(client: TestClient):
    from tests.test_invoices import _invoice_payload, _kontakt

    headers = _onboarded_mandant(client, email="limit-az@example.com")
    kontakt = _kontakt(client, headers)
    for _ in range(7):
        assert client.post("/invoices", headers=headers, json=_invoice_payload(kontakt)).status_code == 201
    for _ in range(7):
        assert client.post("/auth/einladungen", headers=headers, json={}).status_code == 201
