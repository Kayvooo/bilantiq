export const SCHLUESSEL = "bilantiq_mfa_hinweis";

/** Merkt sich für diese Browser-Sitzung, dass das Konto ohne Zwei-Faktor-Anmeldung angemeldet wurde. */
export function markiereMfaHinweis() {
  try {
    sessionStorage.setItem(SCHLUESSEL, "1");
  } catch {
    // ohne Speicher gibt es den Hinweis eben nicht, kein Grund die Anmeldung zu stören
  }
}

export function hinweisOffen(): boolean {
  try {
    return sessionStorage.getItem(SCHLUESSEL) === "1";
  } catch {
    return false;
  }
}
