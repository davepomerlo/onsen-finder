// Offline support for Onsen Finder: app shell cached first, data network-first (falls back to cache offline).
const VERSION = 'onsen-v1';
const SHELL = ['./', 'index.html', 'd3.min.js', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];
const DATA = ['onsen.json', 'prefs.json', 'japan.json', 'sources.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL.concat(DATA))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const isData = url.pathname.endsWith('.json') || url.pathname.endsWith('/') || url.pathname.endsWith('index.html');
  if (isData) {
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); return r;
    }).catch(() => caches.match(e.request).then(r => r || caches.match('index.html'))));
  } else {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => {
      const copy = res.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); return res;
    })));
  }
});
