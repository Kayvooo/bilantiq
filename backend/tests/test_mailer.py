"""Sicherheits- und Zustellbarkeitseigenschaften von app/core/mailer.py (kein echter SMTP-Zugriff)."""
import smtplib
import ssl
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr
from unittest.mock import patch

import pytest

from app.core import mailer


def _senden(**overrides):
    args = dict(
        empfaenger="kunde@example.com", betreff="Rechnung R-1", text="Hallo", anhang_bytes=b"%PDF-1.4",
        anhang_dateiname="Rechnung_R-1.pdf", absender_name="Beispiel GmbH",
    )
    args.update(overrides)
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        mailer.sende_email(**args)
    return mock_smtp


def _gesendete_nachricht(mock_smtp):
    return mock_smtp.return_value.send_message.call_args[0][0]


def test_starttls_mit_geprueftem_zertifikat_vor_login():
    mock_smtp = _senden()
    server = mock_smtp.return_value
    server.starttls.assert_called_once()
    kontext = server.starttls.call_args.kwargs["context"]
    assert isinstance(kontext, ssl.SSLContext)
    assert kontext.verify_mode == ssl.CERT_REQUIRED
    assert kontext.check_hostname is True
    # Reihenfolge: erst TLS, dann Login, dann Versand.
    namen = [aufruf[0] for aufruf in server.method_calls if aufruf[0] in {"starttls", "login", "send_message"}]
    assert namen == ["starttls", "login", "send_message"]


def test_ohne_starttls_beim_server_kein_login_und_kein_versand():
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        server = mock_smtp.return_value
        server.starttls.side_effect = smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")
        with pytest.raises(smtplib.SMTPNotSupportedError):
            mailer.sende_email("kunde@example.com", "Betreff", "Text", b"%PDF", "a.pdf", "Firma")
    server.login.assert_not_called()
    server.send_message.assert_not_called()
    server.quit.assert_called_once()  # Verbindung wird trotzdem sauber beendet


def test_verbindung_hat_timeout():
    mock_smtp = _senden()
    assert mock_smtp.call_args.kwargs["timeout"] == mailer.SMTP_TIMEOUT_SEKUNDEN


def test_fehler_beim_quit_verdeckt_urspruenglichen_fehler_nicht():
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        server = mock_smtp.return_value
        server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth fehlgeschlagen")
        server.quit.side_effect = smtplib.SMTPServerDisconnected("weg")
        with pytest.raises(smtplib.SMTPAuthenticationError):
            mailer.sende_email("kunde@example.com", "Betreff", "Text", b"%PDF", "a.pdf", "Firma")
    server.close.assert_called_once()


def test_absender_mit_umlauten_kodiert_nur_den_namen():
    nachricht = _gesendete_nachricht(_senden(absender_name="Müller & Söhne GmbH"))
    geparst = message_from_bytes(nachricht.as_bytes())
    name, adresse = parseaddr(geparst["From"])
    assert adresse == "noreply@example.invalid"
    assert str(make_header(decode_header(name))) == "Müller & Söhne GmbH"
    # Die Adresse steht lesbar im Kopf und nicht in einem Encoded-Word versteckt.
    assert "<noreply@example.invalid>" in geparst["From"]


def test_date_und_message_id_gesetzt():
    nachricht = _gesendete_nachricht(_senden())
    assert nachricht["Date"].endswith("GMT")
    assert nachricht["Message-ID"].startswith("<") and nachricht["Message-ID"].endswith("@example.invalid>")


def test_zeilenumbrueche_in_betreff_und_absendername_werden_neutralisiert():
    nachricht = _gesendete_nachricht(
        _senden(betreff="Hi\r\nBcc: boese@example.com", absender_name="Firma\r\nBcc: boese@example.com")
    )
    roh = nachricht.as_bytes().decode("utf-8", errors="replace")
    kopf = roh.split("\n\n", 1)[0]
    assert "\nBcc:" not in kopf and "\r\nBcc:" not in kopf
    assert nachricht["Bcc"] is None
    assert nachricht["Subject"] == "Hi Bcc: boese@example.com"


@pytest.mark.parametrize(
    "boese",
    [
        "a@example.com\r\nBcc: boese@example.com",
        "a@example.com, b@example.com",
        "a@example.com;b@example.com",
        "Name <a@example.com>",
        "ohne-at.example.com",
        "a@@example.com",
        "",
    ],
)
def test_ungueltige_empfaenger_werden_vor_dem_verbinden_abgelehnt(boese):
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        with pytest.raises(ValueError):
            mailer.sende_email(boese, "Betreff", "Text", b"%PDF", "a.pdf", "Firma")
    mock_smtp.assert_not_called()


def test_dateiname_wird_bereinigt():
    nachricht = _gesendete_nachricht(_senden(anhang_dateiname='../x"\r\nContent-Type: text/html.pdf'))
    teil = next(p for p in nachricht.walk() if p.get_content_disposition() == "attachment")
    name = teil.get_filename()
    assert "/" not in name and "\n" not in name and '"' not in name
    assert name.endswith(".pdf")


def test_reply_to_optional_und_geprueft():
    nachricht = _gesendete_nachricht(_senden(antwort_an="inhaber@firma.example"))
    assert nachricht["Reply-To"] == "inhaber@firma.example"
    with patch("app.core.mailer.smtplib.SMTP"):
        with pytest.raises(ValueError):
            mailer.sende_email("kunde@example.com", "B", "T", b"%PDF", "a.pdf", "F", antwort_an="x@y.de\r\nBcc: z@y.de")


def test_text_email_nutzt_dieselben_regeln():
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        mailer.sende_text_email("kunde@example.com", "Code\r\nBcc: x@y.de", "Dein Code: 123456", absender_name="Bilantiq")
    server = mock_smtp.return_value
    server.starttls.assert_called_once()
    nachricht = server.send_message.call_args[0][0]
    assert nachricht["Subject"] == "Code Bcc: x@y.de"
    assert nachricht["Message-ID"] and nachricht["Date"]


def test_selbstsigniertes_zertifikat_des_smtp_servers_wird_abgelehnt(monkeypatch, tmp_path):
    """Echte Verbindung zu einem lokalen Mini-SMTP-Server mit selbstsigniertem Zertifikat: kein Login, Handshake scheitert.

    Ohne Zertifikatspruefung (Standardverhalten von smtplib.starttls ohne Kontext) wuerde dieser Versand gelingen.
    """
    import datetime
    import socket
    import threading

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    schluessel = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    zertifikat = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(jetzt - datetime.timedelta(days=1))
        .not_valid_after(jetzt + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(schluessel, hashes.SHA256())
    )
    cert_datei, key_datei = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_datei.write_bytes(zertifikat.public_bytes(serialization.Encoding.PEM))
    key_datei.write_bytes(
        schluessel.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )

    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.load_cert_chain(cert_datei, key_datei)
    server_sock = socket.socket()
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]
    empfangen: list[str] = []

    def bedienen():
        conn, _ = server_sock.accept()
        try:
            f = conn.makefile("rwb", buffering=0)
            f.write(b"220 test ESMTP\r\n")
            while True:
                zeile = f.readline().decode().strip()
                empfangen.append(zeile.split(" ")[0].upper())
                if zeile.upper().startswith("EHLO"):
                    f.write(b"250-test\r\n250 STARTTLS\r\n")
                elif zeile.upper() == "STARTTLS":
                    f.write(b"220 bereit\r\n")
                    try:
                        conn = kontext.wrap_socket(conn, server_side=True)
                    except (ssl.SSLError, OSError):
                        return
                    f = conn.makefile("rwb", buffering=0)
                elif not zeile:
                    return
                else:
                    f.write(b"250 ok\r\n")
        finally:
            conn.close()
            server_sock.close()

    thread = threading.Thread(target=bedienen, daemon=True)
    thread.start()
    monkeypatch.setattr(mailer.settings, "smtp_host", "localhost")
    monkeypatch.setattr(mailer.settings, "smtp_port", port)
    with pytest.raises(ssl.SSLCertVerificationError):
        mailer.sende_email("kunde@example.com", "Betreff", "Text", b"%PDF", "a.pdf", "Firma")
    thread.join(timeout=5)
    assert "AUTH" not in empfangen  # Zugangsdaten wurden nie gesendet
