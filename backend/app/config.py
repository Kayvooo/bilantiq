from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir="/run/secrets",
    )

    # "development" (Standard: lokal, Tests), "staging" oder "production". In staging/production verweigert die App den
    # Start, wenn TRUSTED_HOSTS_RAW fehlt oder "*" enthaelt (Host-Header-Schutz waere sonst still aus).
    app_env: str = "development"
    database_url: str = "sqlite:///./bilantiq_dev.db"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    # "Dieses Geraet merken" bei der MFA-Bestaetigung (LoginForm/MfaChallenge) --
    # gilt nur fuer den ausgestellten Token selbst, kein separates Geraete-Merkmal.
    remember_device_days: int = 30
    mfa_issuer: str = "Bilantiq"
    failed_login_limit: int = 5
    failed_login_lock_minutes: int = 15
    retention_years: int = 10
    # Comma-separated. Local dev only — a real deployment sets this to its actual
    # frontend origin(s), never "*" (this API uses Bearer tokens, not cookies, so a
    # wildcard would work with CORS, but an explicit list stays auditable).
    cors_allowed_origins_raw: str = "http://localhost:5173"
    # Host-Header-Schutz (TrustedHostMiddleware). Default "*" laesst in der lokalen
    # Entwicklung jeden Host durch (auch LAN-IP/TestClient-"testserver"); eine echte
    # Deployment setzt hier die echte Domain, z.B. "api.example.org".
    trusted_hosts_raw: str = "*"
    # Interaktive API-Dokumentation (/docs, /redoc, /openapi.json) zeigt die komplette Angriffsflaeche. Sie ist
    # deshalb standardmaessig AUS; lokal in der .env mit API_DOCS_AKTIV=true einschalten.
    api_docs_aktiv: bool = False
    # Basisordner fuer ALLE Dateien der Instanz (Belege, Logos, Briefpapier, Kontoauszuege, Altrechnungs-Archiv).
    # Jede Instanz braucht ihren eigenen, dauerhaften Speicher; es gibt keinen zentralen Speicher des Projekts.
    # Die Unterordner unten leiten sich daraus ab, solange sie nicht einzeln ueberschrieben werden (nur noetig,
    # wenn z. B. die Kontoauszuege auf ein anderes Laufwerk sollen). Siehe docs/self-hosting.md.
    storage_dir: str = "./data"
    receipt_storage_dir: str | None = None
    receipt_confidence_threshold: float = 0.6
    receipt_max_bytes: int = 15 * 1024 * 1024
    bank_storage_dir: str | None = None
    bank_max_bytes: int = 10 * 1024 * 1024
    import_max_bytes: int = 10 * 1024 * 1024
    # Archiv fuer Rechnungen aus dem Altsystem (PDFs und die Quelldatei der Rechnungsliste).
    altrechnung_storage_dir: str | None = None
    altrechnung_pdf_max_bytes: int = 15 * 1024 * 1024
    altrechnung_pdf_max_dateien: int = 20
    branding_storage_dir: str | None = None
    letterhead_storage_dir: str | None = None
    smtp_port: int = 587  # STARTTLS-Standardport, siehe app/core/mailer.py
    # Versandlimit je Mandant fuer Rechnungen/Angebote/Mahnungen per E-Mail (0 = aus), siehe app/core/mailversand.py.
    email_limit_pro_stunde: int = 30
    email_limit_pro_tag: int = 100
    # Reply-To = Anmelde-Adresse des versendenden Nutzers (macht sie fuer Empfaenger sichtbar).
    email_reply_to_nutzer: bool = True
    # Absenderadresse der Systemmails. Ohne Wert wird SMTP_USER verwendet, sofern es eine E-Mail-Adresse ist.
    # Bewusst kein Default: eine fremde Domain als Absender waere Spoofing und landet im Spam.
    smtp_absender: str | None = None

    # Wer darf sich registrieren? Siehe docs/self-hosting.md, Abschnitt Registrierung.
    #   open           jede Person darf eine neue Firma anlegen (nur fuer bewusst oeffentliche Mehrmandanten-Instanzen)
    #   first_account  nur das allererste Konto der Instanz; danach nur noch per Einladungscode einer bestehenden Firma
    #   closed         keine Selbstregistrierung (auch nicht per Einladungscode); der Owner legt Mitglieder direkt an
    registration_mode: Literal["open", "first_account", "closed"] = "first_account"

    # Lokale KI: standardmaessig deaktiviert und ohne Cloud-Fallback. Sobald aktiviert,
    # spricht Bilantiq nur mit diesem OpenAI-kompatiblen Inference-Endpunkt.
    ai_enabled: bool = False
    ai_base_url: str = "http://ai:8000/v1"
    ai_model: str = "local-model"
    ai_timeout_seconds: float = 30.0
    ai_api_key: str | None = None

    # Pruefung erzeugter XRechnungen gegen die XRechnung-Regeln (siehe app/invoices/e_invoice_validation.py und
    # docs/xrechnung-validierung.md). "aus": keine Pruefung. "warnen": XML wird ausgeliefert, das Ergebnis steht in den
    # Antwort-Headern. "blockieren": ein Fehler oder fehlende Regeln stoppen die Auslieferung (HTTP 422).
    xrechnung_pruefung: Literal["aus", "warnen", "blockieren"] = "warnen"
    # Ordner mit den per scripts/kosit_regeln_holen.py geholten Regeln. Leer: backend/.kosit-regeln.
    xrechnung_regeln_dir: str | None = None

    # No defaults for secrets on purpose: startup fails loudly if .env is missing
    # instead of silently running with a guessable value. See .env.example.
    jwt_secret: str
    # Legacy Fernet-Key bleibt waehrend der kontrollierten Migration lesbar.
    field_encryption_key: str
    email_lookup_secret: str
    # Versionierter AES-256-GCM-Keyring, Format: v1:<base64url-32-byte>[,v2:<...>].
    # Neue Daten werden nur mit DATA_ENCRYPTION_ACTIVE_KID geschrieben; alte Keys
    # bleiben zum Entschluesseln bis nach einer erfolgreichen Rotation vorhanden.
    data_encryption_keys: str
    data_encryption_active_kid: str = "v1"
    blind_index_secret: str
    # SMTP ist OPTIONAL. Ohne SMTP_HOST/SMTP_USER/SMTP_PASSWORD (und eine Absenderadresse) startet die App trotzdem,
    # aber E-Mail-Versand, "Passwort vergessen" und die E-Mail-Bestaetigung bei Adressaenderung sind abgeschaltet und
    # antworten mit einer klaren Meldung (HTTP 503), nichts wird still verschluckt. Siehe app/core/mailer.py.
    smtp_host: str | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    # Basis-URL des Frontends fuer Links in E-Mails (Passwort zuruecksetzen). Bewusst OHNE Default: Ein geratener Wert
    # (z. B. localhost) wuerde in Produktion Links ins Leere schicken. Ohne Wert wird keine Reset-Mail versendet und
    # der Fehler protokolliert (die Antwort bleibt aus Gruenden der Konto-Enumeration trotzdem unveraendert).
    app_frontend_url: str | None = None

    @model_validator(mode="after")
    def _leite_speicherordner_ab(self) -> "Settings":
        """Unterordner aus STORAGE_DIR ableiten, solange sie nicht ausdruecklich gesetzt wurden."""
        roh = self.storage_dir.strip()
        basis = roh.rstrip("/\\") or ("" if roh.startswith("/") else ".")
        for feld, unterordner in (
            ("receipt_storage_dir", "receipts"),
            ("bank_storage_dir", "bank"),
            ("altrechnung_storage_dir", "altrechnungen"),
            ("branding_storage_dir", "branding"),
            ("letterhead_storage_dir", "briefpapier"),
        ):
            if not getattr(self, feld):
                setattr(self, feld, f"{basis}/{unterordner}")
        return self

    @model_validator(mode="after")
    def _normalisiere_smtp(self) -> "Settings":
        """Leere Werte und der Platzhalter SET_ME (aus init-secrets.sh) gelten als "nicht gesetzt"."""
        for feld in ("smtp_host", "smtp_user", "smtp_password", "smtp_absender"):
            wert = getattr(self, feld)
            if wert is not None and (not wert.strip() or wert.strip() == "SET_ME"):
                setattr(self, feld, None)
        return self

    @model_validator(mode="after")
    def _lehne_platzhalter_secrets_ab(self) -> "Settings":
        """Die Platzhalter aus .env.example (z. B. "generate-with-openssl-rand-hex-32") sind oeffentlich bekannt. Wer die
        Datei kopiert und vergisst, sie zu ersetzen, wuerde sonst mit einem erratbaren Schluessel laufen."""
        for feld in ("jwt_secret", "field_encryption_key", "email_lookup_secret", "data_encryption_keys", "blind_index_secret"):
            wert = getattr(self, feld).strip().lower()
            if "generate-with" in wert or "replace-with" in wert or wert == "set_me":
                raise ValueError(
                    f"{feld.upper()} enthaelt noch den Platzhalter aus .env.example. Bitte einen eigenen, zufaelligen Wert "
                    "erzeugen (siehe docs/self-hosting.md, Abschnitt Secrets) und niemals einen oeffentlich bekannten Wert verwenden."
                )
        return self

    @model_validator(mode="after")
    def _pruefe_umgebung(self) -> "Settings":
        if self.app_env not in {"development", "staging", "production"}:
            raise ValueError("APP_ENV muss development, staging oder production sein.")
        if self.app_env != "development" and (not self.trusted_hosts or "*" in self.trusted_hosts):
            raise ValueError(
                f"APP_ENV={self.app_env}: TRUSTED_HOSTS_RAW muss auf die echte(n) Domain(s) gesetzt sein "
                "(z. B. api.example.org), nicht leer und nicht '*'."
            )
        return self

    @property
    def absender_adresse(self) -> str | None:
        """Absenderadresse der Systemmails: SMTP_ABSENDER, sonst SMTP_USER, falls das eine Adresse ist."""
        if self.smtp_absender:
            return self.smtp_absender.strip()
        if self.smtp_user and "@" in self.smtp_user:
            return self.smtp_user.strip()
        return None

    @property
    def email_aktiv(self) -> bool:
        """True nur, wenn Server, Zugangsdaten und eine Absenderadresse vorhanden sind."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.absender_adresse)

    @property
    def cors_allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allowed_origins_raw.split(",") if origin.strip()]
        if "*" in origins:
            # Die API laeuft mit allow_credentials=True; ein Platzhalter wuerde jeder Webseite Zugriff erlauben.
            raise ValueError("CORS_ALLOWED_ORIGINS_RAW darf kein '*' enthalten, bitte die echten Origins eintragen.")
        return origins

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts_raw.split(",") if host.strip()]


settings = Settings()
