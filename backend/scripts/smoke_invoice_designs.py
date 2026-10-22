"""Real HTTP smoke test on loopback, isolated database and fictional tenant only."""
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.preview_invoice_designs import isolated_environment


def main():
    isolated_environment()
    with tempfile.TemporaryDirectory(prefix="bilantiq-design-smoke-") as directory:
        os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(directory) / "smoke.db")
        import httpx
        import pyotp
        import uvicorn
        from app.main import app
        from app.db import engine
        from app.core.document_pdf import GUELTIGE_VORLAGEN

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.1)
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
                assert client.get("/health").status_code == 200
                registration = client.post("/auth/register", json={"email": "design@example.com",
                    "password": "Fictional-design-smoke-2026!", "firmenname": "Muster Studio"})
                assert registration.status_code == 201, registration.status_code
                pre = {"Authorization": "Bearer " + registration.json()["pre_auth_token"]}
                secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
                token = client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()}).json()["access_token"]
                headers = {"Authorization": "Bearer " + token}
                tenant_id = client.get("/auth/me", headers=headers).json()["mandant_id"]
                for template in GUELTIGE_VORLAGEN:
                    response = client.get("/auth/mandant/rechnungsvorlage/vorschau", headers=headers,
                        params={"vorlage": template, "sprache": "en", "zeige_artikelnummer": True,
                                "zeige_seitenzahlen": True, "akzentfarbe": "#FFEEAA"})
                    assert response.status_code == 200, (template, response.status_code)
                    assert response.content.startswith(b"%PDF")
                print("Live-Smoke: Health, Registrierung/MFA und 11 PDF-Vorlagen über HTTP erfolgreich.")
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            engine.dispose()


if __name__ == "__main__":
    main()
