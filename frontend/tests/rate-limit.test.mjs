import assert from "node:assert/strict";
import {test} from "node:test";
import {installiereRateLimitHinweis, rateLimitMeldung, retryAfterSekunden} from "../src/lib/rateLimit.ts";

test("Retry-After in Sekunden und als HTTP-Datum", () => {
  assert.equal(retryAfterSekunden("90"), 90);
  const jetzt = Date.parse("2026-10-14T10:00:00Z");
  assert.equal(retryAfterSekunden("Wed, 14 Oct 2026 10:05:00 GMT", jetzt), 300);
  assert.equal(retryAfterSekunden("Wed, 14 Oct 2026 09:00:00 GMT", jetzt), 0);
  assert.equal(retryAfterSekunden("irgendwas"), null);
  assert.equal(retryAfterSekunden(null), null);
});

test("Meldung nennt die Wartezeit, sonst Servertext, sonst allgemeiner Text", () => {
  assert.equal(rateLimitMeldung("30"), "Zu viele Versuche. Bitte versuche es in 30 Sekunden erneut.");
  assert.equal(rateLimitMeldung("60"), "Zu viele Versuche. Bitte versuche es in 1 Minute erneut.");
  assert.equal(rateLimitMeldung("301"), "Zu viele Versuche. Bitte versuche es in 6 Minuten erneut.");
  assert.equal(rateLimitMeldung("900"), "Zu viele Versuche. Bitte versuche es in 15 Minuten erneut.");
  assert.equal(rateLimitMeldung(null, "Konto gesperrt."), "Konto gesperrt.");
  assert.equal(rateLimitMeldung(null, null), "Zu viele Versuche. Bitte versuche es später erneut.");
});

test("fetch-Huelle schreibt nur 429 um und laesst alles andere unveraendert", async () => {
  const antworten = [
    new Response(JSON.stringify({detail: "Zu viele Versuche. Bitte warte einen Moment."}), {status: 429, headers: {"Retry-After": "120"}}),
    new Response(JSON.stringify({detail: "Falsch"}), {status: 400}),
    new Response("{}", {status: 429}),
  ];
  const ziel = {fetch: async () => antworten.shift()};
  installiereRateLimitHinweis(ziel);
  const a = await ziel.fetch("/x");
  assert.equal(a.status, 429);
  assert.equal(a.headers.get("Retry-After"), "120");
  assert.equal((await a.json()).detail, "Zu viele Versuche. Bitte versuche es in 2 Minuten erneut.");
  const b = await ziel.fetch("/x");
  assert.equal(b.status, 400);
  assert.equal((await b.json()).detail, "Falsch");
  const c = await ziel.fetch("/x");
  assert.equal((await c.json()).detail, "Zu viele Versuche. Bitte versuche es später erneut.");
});
