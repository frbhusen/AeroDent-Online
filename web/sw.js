// AeroDent service worker.
// Caches ONLY the public application shell (HTML/JS/CSS/icons) so the offline PWA mode works.
// It never caches /api/ responses, so no patient, clinic, or session data ever lands in the
// Cache API. __ASSET_VERSION__ is replaced by the server with a content hash of web/, so every
// deploy gets a fresh cache and old caches are deleted on activation. See docs/CACHING.md.
const VERSION = "__ASSET_VERSION__";
const CACHE = `aerodent-shell-${VERSION}`;
const SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./i18n.js",
  "./db.js",
  "./js/api.js",
  "./js/state.js",
  "./js/core.js",
  "./js/ui.js",
  "./js/auth.js",
  "./js/patients.js",
  "./js/odontogram.js",
  "./js/treatments.js",
  "./js/treatmentPlans.js",
  "./js/appointments.js",
  "./js/prescriptions.js",
  "./js/xrays.js",
  "./js/timeline.js",
  "./js/backup.js",
  "./js/admin.js",
  "./js/auditLogs.js",
  "./js/commandPalette.js",
  "./js/hr.js",
  "./js/inventory.js",
  "./js/events.js",
  "./js/app.js",
];

function versioned(path) {
  if (path === "./" || path === "./index.html") return path;
  return `${path}?v=${VERSION}`;
}

self.addEventListener("install", (event) =>
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL.map(versioned)))
      .then(() => self.skipWaiting()),
  ),
);

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  ),
);

function isCacheable(response) {
  if (!response || response.status !== 200 || response.type !== "basic") return false;
  // Anything the server marks private is per-user and must never be stored.
  return !/\bprivate\b/i.test(response.headers.get("Cache-Control") || "");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Never intercept or cache API traffic (clinical data, X-ray images, session state).
  if (url.pathname.startsWith("/api/") || url.pathname === "/sw.js") return;

  // App shell navigations: always try the network first so a new deploy is picked up and
  // the server can apply no-store; fall back to the cached shell only when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (isCacheable(response)) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put("./index.html", copy));
          }
          return response;
        })
        .catch(() => caches.match("./index.html")),
    );
    return;
  }

  // Content-hashed assets (?v=<version>) never change: serve from cache, fill on miss.
  if (url.searchParams.get("v") === VERSION) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (isCacheable(response)) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
    return;
  }

  // Anything else static: network first, cached copy only as an offline fallback.
  event.respondWith(fetch(request).catch(() => caches.match(request, { ignoreSearch: true })));
});
