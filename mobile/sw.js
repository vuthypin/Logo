// Cache pour un fonctionnement hors ligne : l'interface est servie depuis le cache,
// les données sont toujours demandées au réseau d'abord (dernière version connue sinon).
const CACHE = "cac40-v1";
const SHELL = [
  "./",
  "index.html",
  "styles.css",
  "app.js",
  "vendor/chart-4.4.1.umd.js",
  "manifest.webmanifest",
  "icons/icon.svg",
  "icons/icon-192.png",
  "icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  if (url.pathname.endsWith("/data.json")) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("data.json", copy));
          return res;
        })
        .catch(() => caches.match("data.json")),
    );
    return;
  }

  // Interface : réseau d'abord pour récupérer les mises à jour, cache si hors ligne.
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request)),
  );
});
