/* 导诊台 Service Worker · 缓存应用壳，API 网络优先不落地 */
const CACHE = 'triage-shell-v16-guardrail-020';
const SHELL = [
  './',
  './index.html',
  './css/styles.css',
  './js/app.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  // 同源反代（部署）：/patient-api/、/doctor-api/；直连（本地）：/api/ 或 8001/8000 端口；其它跨域一律不缓存
  return url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/patient-api/') ||
    url.pathname.startsWith('/doctor-api/') ||
    url.port === '8001' || url.port === '8000' ||
    url.origin !== self.location.origin;
}

function isRuntimeConfig(url) {
  return url.origin === self.location.origin && /\/config\.js$/.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // 运行时配置：网络优先（部署改配置立即生效），离线回退缓存
  if (isRuntimeConfig(url)) {
    event.respondWith(
      fetch(req, { cache: 'no-store' })
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((c) => c || new Response('window.APP_CONFIG = window.APP_CONFIG || {};', {
          headers: { 'Content-Type': 'application/javascript; charset=utf-8' }
        })))
    );
    return;
  }

  // Never cache API as source of truth — network only
  if (isApiRequest(url)) {
    event.respondWith(
      fetch(req).catch(() =>
        new Response(JSON.stringify({ error: 'offline', message: '网络不可用，请稍后重试' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    return;
  }

  // App shell: cache-first with network update
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          if (res && res.ok && url.origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => cached || caches.match('./index.html').then((h) =>
          h || new Response(
            '<!DOCTYPE html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>导诊台</title><body style="font-family:system-ui;padding:24px;text-align:center"><h1>导诊台</h1><p>当前离线，请检查网络后重试。</p><p style="color:#64748b;font-size:14px">辅助导诊，不能替代面诊</p></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          )
        ));
      return cached || network;
    })
  );
});
