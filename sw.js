/*
Minimal service worker - exists only so the browser treats this page as an
installable app (custom icon, no address bar when opened from the home
screen icon). It deliberately does NOT cache index.html, history.html, or
any data - this is a live weather dashboard, and caching the actual
content would risk showing stale readings, which is exactly the bug that
had to be fixed on the D3D site earlier. Only the truly static app-shell
files (manifest, icons) are cached; everything else always goes to the
network.
*/

var CACHE_NAME = 'meriden-weather-shell-v1';
var SHELL_URLS = ['manifest.json', 'icon-192.png', 'icon-512.png'];

self.addEventListener('install', function (event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(SHELL_URLS);
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') return;

  var isShell = SHELL_URLS.some(function (path) {
    return event.request.url.indexOf(path) !== -1;
  });

  if (isShell) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        return cached || fetch(event.request);
      })
    );
    return;
  }

  // Everything else (index.html, history.html, the CSV data) - always
  // fetch fresh from the network. Never serve a cached copy.
  event.respondWith(fetch(event.request));
});
