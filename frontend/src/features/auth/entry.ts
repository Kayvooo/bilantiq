/** Public website hint only; never authenticates a user. */
export function initialAuthView(search: string): "login" | "register" {
  return new URLSearchParams(search).get("ansicht") === "anmelden" ? "login" : "register";
}
