// Service Worker fuer die installierte Bilantiq-App.
// Gecacht wird nur die App-Huelle (HTML, JS, CSS, Schriften, Icons) derselben Origin.
// API-Antworten (Buchhaltungsdaten, Tokens, PDFs) laufen immer direkt ans Netz und
// landen nie im Cache: Die API liegt auf einer anderen Origin und wird hier ausgelassen.

const SHELL_CACHE = "bilantiq-shell-v1";
const ASSET_CACHE = "bilantiq-assets-v1";
const KNOWN_CACHES = [SHELL_CACHE, ASSET_CACHE];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(["/", "/brand/site.webmanifest", "/favicon.svg", "/brand/bilantiq_icon_192.png"]))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => !KNOWN_CACHES.includes(key)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  // Vite legt gehashte, unveraenderliche Dateien unter /assets/ ab.
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/brand/")) {
    event.respondWith(cacheFirst(request));
  }
});

async function networkFirstNavigation(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put("/", response.clone());
    return response;
  } catch {
    const cached = await cache.match("/");
    if (cached) return cached;
    return new Response("Bilantiq ist offline und noch nicht geladen. Bitte mit dem Internet verbinden.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSET_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}
