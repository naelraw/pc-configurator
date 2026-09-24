// Service worker minimal de PC Radar : rend le site installable et affiche une
// page « Pas de connexion » hors ligne. Il ne met AUCUNE page ni donnée en
// cache (les prix doivent toujours être ceux du jour).
const OFFLINE = '/static/offline.html';
const CACHE = 'pcradar-hors-ligne-v1';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll([OFFLINE, '/static/style.css', '/static/favicon.svg'])));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return;  // tout le reste : réseau normal
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
});
