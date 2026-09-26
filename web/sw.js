const CACHE = "aerodent-online-v3";
const ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./i18n.js",
  "./js/api.js",
  "./db.js",
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
  "./js/inventory.js",
  "./js/events.js",
  "./js/app.js",
];

self.addEventListener("install", (event) =>
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
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
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  ),
);

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);
  // Never cache or intercept API requests
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200 && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() =>
        caches
          .match(event.request)
          .then((cached) => cached || caches.match("./index.html")),
      ),
  );
});
