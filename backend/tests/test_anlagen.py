from fastapi.testclient import TestClient

from app.anlagen.afa import berechne_afa_plan
from decimal import Decimal
from datetime import date
from tests.test_invoices import _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def test_afa_plan_summe_ergibt_exakt_die_anschaffungskosten():
    plan = berechne_afa_plan(date(2026, 6, 15), Decimal("3000.00"), 3)
    summe = sum((eintrag["afa_betrag"] for eintrag in plan), Decimal("0"))
    assert summe == Decimal("3000.00")
    assert plan[-1]["restbuchwert_ende"] == Decimal("0.00")


def test_afa_plan_erstes_jahr_ist_monatsgenau():
    # Anschaffung im Juni: 7 von 12 Monaten (Jun-Dez) im ersten Jahr
    plan = berechne_afa_plan(date(2026, 6, 1), Decimal("1200.00"), 3)
    jahres_afa = Decimal("400.00")  # 1200 / 3
    erwartetes_erstes_jahr = (jahres_afa * 7 / 12).quantize(Decimal("0.01"))
    assert plan[0]["afa_betrag"] == erwartetes_erstes_jahr
    assert plan[0]["jahr"] == 2026


def test_gwg_wird_sofort_voll_abgeschrieben():
    plan = berechne_afa_plan(date(2026, 3, 1), Decimal("500.00"), 5)
    assert len(plan) == 1
    assert plan[0]["afa_betrag"] == Decimal("500.00")
    assert plan[0]["restbuchwert_ende"] == Decimal("0.00")


def test_create_anlage_und_uebersicht(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.post(
        "/anlagen", headers=headers,
        json={"bezeichnung": "Laptop", "anschaffungsdatum": "2026-06-01", "anschaffungskosten_netto": "1200.00", "nutzungsdauer_jahre": 3},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["ist_gwg"] is False
    assert len(body["afa_plan"]) == 4  # 7/12, voll, voll, 5/12

    uebersicht = client.get("/anlagen?jahr=2026", headers=headers).json()
    assert len(uebersicht["anlagen"]) == 1
    assert float(uebersicht["afa_gesamt_jahr"]) == float(body["afa_plan"][0]["afa_betrag"])


def test_anlagen_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    client.post(
        "/anlagen", headers=kevin_headers,
        json={"bezeichnung": "Laptop", "anschaffungsdatum": "2026-01-01", "anschaffungskosten_netto": "1200.00", "nutzungsdauer_jahre": 3},
    )

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    body = client.get("/anlagen", headers=lea_headers).json()
    assert body["anlagen"] == []
    assert float(body["afa_gesamt_jahr"]) == 0.0
