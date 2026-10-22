from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

import pikepdf
import pytest

from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant


@pytest.mark.parametrize("contact_kind", ["foreign", "missing"])
def test_invoice_preview_security_rejects_non_members_before_rendering(client, contact_kind):
    foreign = _onboarded_mandant(client, email="foreign@example.com")
    foreign_id = client.get("/auth/me", headers=foreign).json()["user_id"]
    headers = _onboarded_mandant(client, email="owner@example.com")
    payload = _invoice_payload(_kontakt(client, headers))
    payload.update(
        interne_kontaktperson_user_id=foreign_id if contact_kind == "foreign" else str(uuid4()),
        fusstext="[%KONTAKTPERSON%]",
    )

    with patch("app.invoices.routes.render_invoice_pdf", return_value=b"%PDF") as render:
        response = client.post("/invoices/vorschau", headers=headers, json=payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Interne Kontaktperson gehoert nicht zu diesem Mandanten."}
    render.assert_not_called()
    assert client.get("/invoices", headers=headers).json() == []


def test_invoice_preview_security_allows_own_member_without_saving(client):
    headers = _onboarded_mandant(client, email="owner@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["user_id"]
    payload = _invoice_payload(_kontakt(client, headers))
    payload.update(interne_kontaktperson_user_id=user_id, fusstext="[%KONTAKTPERSON%]")

    response = client.post("/invoices/vorschau", headers=headers, json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    with pikepdf.Pdf.open(BytesIO(response.content)) as pdf:
        streams = []
        for page in pdf.pages:
            contents = page.obj.Contents
            parts = contents if isinstance(contents, pikepdf.Array) else [contents]
            streams.extend(part.read_bytes() for part in parts)
        assert b"owner@example.com" in b"\n".join(streams)
    assert client.get("/invoices", headers=headers).json() == []
