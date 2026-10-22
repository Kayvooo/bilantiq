import assert from "node:assert/strict";
import {test} from "node:test";
import {dezimalEingabe} from "../src/lib/decimalInput.ts";

test("Dezimalkomma wird zu Punkt, ohne Rundung oder Umformung", () => {
  assert.equal(dezimalEingabe("1,5"), "1.5");
  assert.equal(dezimalEingabe("12,50"), "12.50");
  assert.equal(dezimalEingabe("0,"), "0.");
  assert.equal(dezimalEingabe("19"), "19");
  assert.equal(dezimalEingabe("1.5"), "1.5");
  assert.equal(dezimalEingabe(""), "");
});

test("Mit Komma getippte Werte ergeben gueltige Zahlen fuer die Summenberechnung", () => {
  assert.equal(Number("1,5"), Number.NaN);
  assert.equal(Number(dezimalEingabe("1,5")), 1.5);
});
