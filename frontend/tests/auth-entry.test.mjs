import assert from "node:assert/strict";
import {test} from "node:test";
import {initialAuthView} from "../src/features/auth/entry.ts";
test("explicit website login", () => assert.equal(initialAuthView("?ansicht=anmelden"), "login"));
test("registration and default stay backwards compatible", () => {
  for (const query of ["", "?ansicht=registrieren", "?ansicht=unbekannt", "?ansicht=https://example.com"]) assert.equal(initialAuthView(query), "register");
});
import {EINLADUNGSCODE_LAENGE, normalisiereEinladungscode} from "../src/features/auth/einladungscode.ts";
test("Einladungscode: 12 Zeichen, Gross, ohne Leer-/Bindestriche", () => {
  assert.equal(EINLADUNGSCODE_LAENGE, 12);
  assert.equal(normalisiereEinladungscode(" 3f9a-1c7d 02be "), "3F9A1C7D02BE");
  assert.equal(normalisiereEinladungscode("3F9A1C7D02BEFFFF"), "3F9A1C7D02BE");
});
