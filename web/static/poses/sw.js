/* poses/sw.js — Service worker du mode photographe jour J (jalon 3).
   Servi in-scope à /poses/sw.js (périmètre /poses/) pour pouvoir intercepter
   /poses/field/… ET les assets /poses/a/… (hors périmètre = non interceptable).

   Stratégies :
     - navigations /poses/field/…  : NETWORK-FIRST (frais en ligne, snapshot en cache hors-ligne)
     - assets /poses/a/… + manifest : CACHE-FIRST
     - tout le reste / POST d'API    : passthrough réseau (la file de synchro vit dans la page)

   Bump CACHE à chaque changement d'asset pour purger l'ancien cache. */
const CACHE = "poses-field-v3";

// Pré-cache : garantit que les assets sont dispo hors-ligne DÈS la 1re visite,
// même s'ils avaient été chargés avant que le SW prenne le contrôle.
// (URLs versionnées : les tenir synchro avec field.html + bumper CACHE.)
const PRECACHE = [
  "/poses/a/field.css?v=1",
  "/poses/a/field.js?v=3",
  "/poses/app.webmanifest",
  "/poses/a/icons/icon-192.png"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE)
      .then(function (c) { return c.addAll(PRECACHE); })
      .catch(function () {})
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil((async function () {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter(function (k) { return k.indexOf("poses-field-") === 0 && k !== CACHE; })
          .map(function (k) { return caches.delete(k); })
    );
    await self.clients.claim();
  })());
});

// La page demande explicitement la mise en cache de sa propre navigation, pour
// garantir le mode hors-ligne DÈS la première visite (le 1er chargement a lieu
// avant que le SW ne contrôle la page, donc la navigation n'est pas cachée seule).
self.addEventListener("message", function (e) {
  var data = e.data || {};
  if (data.type === "cache-self" && data.url) {
    e.waitUntil(caches.open(CACHE).then(function (c) { return c.add(data.url); }).catch(function () {}));
  }
});

function isField(url) { return url.pathname.indexOf("/poses/field/") !== -1; }
function isAsset(url) {
  return url.pathname.indexOf("/poses/a/") !== -1 ||
         url.pathname.indexOf("/poses/app.webmanifest") !== -1;
}

self.addEventListener("fetch", function (e) {
  const req = e.request;
  if (req.method !== "GET") return;               // API POST -> réseau direct
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (isField(url)) {
    e.respondWith((async function () {
      try {
        const res = await fetch(req);
        const cache = await caches.open(CACHE);
        cache.put(req, res.clone());
        return res;
      } catch (err) {
        const cached = await caches.match(req);
        if (cached) return cached;
        return new Response(
          "<h1>Hors ligne</h1><p>Cette check-list n'a pas encore été ouverte en ligne une première fois.</p>",
          { headers: { "Content-Type": "text/html; charset=utf-8" }, status: 503 }
        );
      }
    })());
    return;
  }

  if (isAsset(url)) {
    e.respondWith((async function () {
      const cached = await caches.match(req);
      if (cached) return cached;
      try {
        const res = await fetch(req);
        const cache = await caches.open(CACHE);
        cache.put(req, res.clone());
        return res;
      } catch (err) {
        return cached || Response.error();
      }
    })());
  }
});
