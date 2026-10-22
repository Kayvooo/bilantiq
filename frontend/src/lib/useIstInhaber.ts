import { useEffect, useState } from "react";
import { me } from "../features/auth/api";

/** "laedt": noch keine Antwort von /auth/me (oder Fehler) -- Inhaber-Funktionen werden dann weder angeboten
 * noch wird ein Mitglied behauptet. "inhaber" = Rolle owner, "mitglied" = jede andere Rolle. */
export type RollenStatus = "laedt" | "inhaber" | "mitglied";

/** Rolle des angemeldeten Nutzers aus /auth/me. Ohne Token (null) wird nichts geladen. */
export function useRollenStatus(accessToken: string | null): RollenStatus {
  const [stand, setStand] = useState<{ token: string; status: RollenStatus } | null>(null);
  useEffect(() => {
    if (!accessToken) return;
    let aktiv = true;
    me(accessToken)
      .then((profil) => { if (aktiv) setStand({ token: accessToken, status: profil.rolle === "owner" ? "inhaber" : "mitglied" }); })
      .catch(() => {});
    return () => { aktiv = false; };
  }, [accessToken]);
  // Ein Ergebnis zu einem anderen Token (Kontowechsel) zaehlt nicht.
  return accessToken && stand?.token === accessToken ? stand.status : "laedt";
}

/** true, wenn der angemeldete Nutzer Inhaber (owner) des Mandanten ist. Bis die Antwort da
 * ist und bei Fehlern: false, damit Inhaber-Funktionen nie versehentlich angeboten werden. */
export function useIstInhaber(accessToken: string): boolean {
  return useRollenStatus(accessToken) === "inhaber";
}
