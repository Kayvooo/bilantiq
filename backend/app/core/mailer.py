"""Ausgehender E-Mail-Versand fuer Rechnungen/Angebote/Mahnungen als PDF-Anhang.

Bewusst stdlib-only (smtplib + email.mime), keine Drittanbieter-SDK und kein
Transactional-Email-Service: Wer die Instanz betreibt, kann einen beliebigen SMTP-Anbieter
eintragen (inkl. Gmail), siehe app.config.settings.smtp_* und backend/.env.example.
TLS laeuft ueber STARTTLS auf dem konfigurierten Port (Standard 587), nicht ueber
implizites TLS auf Port 465.

Sicherheits- und Zustellbarkeitsregeln (siehe docs/email-zustellung.md):
- STARTTLS ist Pflicht und das Zertifikat des SMTP-Servers wird geprueft (Zertifikatskette und Hostname,
  ssl.create_default_context()). smtplib selbst wuerde ohne Kontext ungeprueft verschluesseln
  (ssl._create_stdlib_context ist ein "unverified context"). Die Anmeldung erfolgt erst nach dem TLS-Aufbau;
  bietet der Server kein STARTTLS an, bricht der Versand ab, bevor Zugangsdaten gesendet werden.
- Kopfzeilen (Betreff, Absendername, Dateiname) werden von Steuerzeichen/Zeilenumbruechen bereinigt, Adressen
  streng geprueft (Header-Injection).
- Absender wird mit email.utils.formataddr gebildet, damit Umlaute nur den Namen, nicht die Adresse kodieren.
- Date und Message-ID werden gesetzt (fehlen sie, bewerten Spamfilter die Nachricht schlechter).
- Verbindung hat ein Timeout, damit ein haengender SMTP-Server keinen Request unbegrenzt blockiert.

SMTP ist optional (``settings.email_aktiv``). Ohne Konfiguration wirft jeder Versuch ``EmailNichtEingerichtet``; die
Routen uebersetzen das in HTTP 503 mit einer verstaendlichen Meldung, es wird nichts still verschluckt.

Gleiche Ebene wie app/core/branding_storage.py bzw. app/core/letterhead_storage.py:
eine Infrastruktur-Utility, kein eigenes Business-Paket.
"""
import re
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import Message
from email.utils import formataddr, formatdate, make_msgid

from app.config import settings

SMTP_TIMEOUT_SEKUNDEN = 30

EMAIL_NICHT_EINGERICHTET = (
    "E-Mail ist auf dieser Bilantiq-Instanz nicht eingerichtet (SMTP_HOST, SMTP_USER, SMTP_PASSWORD und eine "
    "Absenderadresse fehlen). Der Versand per E-Mail und „Passwort vergessen“ sind deshalb abgeschaltet. "
    "Bitte die Betreiberin oder den Betreiber der Instanz ansprechen (siehe docs/self-hosting.md)."
)


class EmailNichtEingerichtet(RuntimeError):
    """SMTP ist auf dieser Instanz nicht konfiguriert. Wird nie still verschluckt: Aufrufer melden es weiter."""

    def __init__(self) -> None:
        super().__init__(EMAIL_NICHT_EINGERICHTET)

_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f  ]+")
_UNGUELTIG_IN_ADRESSE = re.compile(r"[\x00-\x20\x7f,;<>\"()\[\]\\:]")
_UNGUELTIG_IM_DATEINAMEN = re.compile(r"[\x00-\x1f\x7f\"/\;]+")


def _kopfwert(wert: str) -> str:
    """Macht aus beliebigem Text einen sicheren einzeiligen Kopfzeilenwert (Zeilenumbrueche -> Leerzeichen)."""
    return _STEUERZEICHEN.sub(" ", wert).strip()


def _adresse(wert: str, feld: str) -> str:
    """Akzeptiert nur eine einzelne, schlichte Adresse. Alles andere ist ein Fehler, kein stilles Bereinigen."""
    adresse = wert.strip()
    teile = adresse.split("@")
    if len(teile) != 2 or not teile[0] or not teile[1] or _UNGUELTIG_IN_ADRESSE.search(adresse):
        raise ValueError(f"Ungueltige E-Mail-Adresse im Feld {feld}.")
    return adresse


def _dateiname(wert: str) -> str:
    name = _UNGUELTIG_IM_DATEINAMEN.sub("_", wert).strip(" .")
    return name or "anhang"


def _absender() -> str:
    adresse = settings.absender_adresse
    if not adresse:
        raise EmailNichtEingerichtet()
    return adresse


def _absender_domain() -> str:
    return _absender().rsplit("@", 1)[-1]


def _kopf_setzen(nachricht: Message, empfaenger: str, betreff: str, absender_name: str, antwort_an: str | None) -> None:
    nachricht["From"] = formataddr((_kopfwert(absender_name), _adresse(_absender(), "SMTP_ABSENDER")))
    nachricht["To"] = _adresse(empfaenger, "Empfaenger")
    nachricht["Subject"] = _kopfwert(betreff)
    nachricht["Date"] = formatdate(localtime=False, usegmt=True)
    nachricht["Message-ID"] = make_msgid(domain=_absender_domain())
    if antwort_an:
        nachricht["Reply-To"] = _adresse(antwort_an, "Antwort-an")


def _sende(nachricht: Message) -> None:
    """STARTTLS mit Zertifikatspruefung, erst danach Login und Versand."""
    if not settings.email_aktiv:
        raise EmailNichtEingerichtet()
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SEKUNDEN)
    try:
        # Wirft SMTPNotSupportedError, wenn der Server kein STARTTLS anbietet: dann kein Login, kein Klartext.
        server.starttls(context=ssl.create_default_context())
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(nachricht)
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            # Nach einem Fehler ist die Verbindung oft schon weg; der urspruengliche Fehler soll nicht verdeckt werden.
            server.close()


def sende_email(
    empfaenger: str,
    betreff: str,
    text: str,
    anhang_bytes: bytes,
    anhang_dateiname: str,
    absender_name: str,
    antwort_an: str | None = None,
) -> None:
    """Verschickt eine einzelne Plaintext-E-Mail mit genau einem PDF-Anhang.

    Kein HTML-Template, kein Bulk-/Mailmerge-Versand, keine Zustellbestaetigung --
    ein Dokument an einen Empfaenger, synchron waehrend des Request. Wirft die
    smtplib-Exception unveraendert weiter, falls der Versand fehlschlaegt (z.B.
    falsche Zugangsdaten oder Host nicht erreichbar); der aufrufende Router faengt
    das nicht ab, sodass ein fehlgeschlagener Versand nie faelschlich als Erfolg
    (versendet_am gesetzt) verbucht wird. Ungueltige Adressen fuehren zu ValueError,
    bevor eine Verbindung aufgebaut wird.

    `antwort_an` setzt einen Reply-To (z. B. die Adresse des Mandanten), da der Absender
    selbst die Systemadresse smtp_absender ist. Die Aufrufer uebergeben ihn derzeit noch nicht.
    """
    nachricht = MIMEMultipart()
    _kopf_setzen(nachricht, empfaenger, betreff, absender_name, antwort_an)
    nachricht.attach(MIMEText(text, "plain", "utf-8"))

    anhang = MIMEApplication(anhang_bytes, _subtype="pdf")
    anhang.add_header("Content-Disposition", "attachment", filename=_dateiname(anhang_dateiname))
    nachricht.attach(anhang)

    _sende(nachricht)


def sende_text_email(
    empfaenger: str, betreff: str, text: str, absender_name: str = "Bilantiq", antwort_an: str | None = None
) -> None:
    """Versendet eine reine Plaintext-Sicherheitsmail ohne Anhang."""
    nachricht = MIMEText(text, "plain", "utf-8")
    _kopf_setzen(nachricht, empfaenger, betreff, absender_name, antwort_an)
    _sende(nachricht)
