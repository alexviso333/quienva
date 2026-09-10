// Vercel Edge Middleware
// -----------------------------------------------------------------------------
// Serves the FAST server-rendered (SSR) homepage at "/" instead of the
// client-rendered React shell (build/index.html). Only the EXACT "/" path is
// affected (config.matcher below).
//
// SAFETY: On ANY problem (SSR origin down, non-200, wrong content-type, network
// error, TIMEOUT) the middleware returns nothing, so Vercel simply falls back to
// serving the normal static SPA exactly like today. It therefore CANNOT break
// the site. Every other route is untouched, and the native iOS/Android app is
// unaffected because it loads its OWN bundled index.html locally (Capacitor
// webDir), never from the web.
//
// PERFORMANCE: the SSR origin is on Render's free tier which SLEEPS after
// inactivity, so the first hit could hang for several seconds ("quienva.me
// tarda 4s en abrir"). We now race the fetch against a timeout:
//   • Real people  → short timeout (1.5s). If the SSR is cold/slow we instantly
//     fall back to the static SPA (served from Vercel's CDN → opens immediately),
//     instead of making the visitor wait for the backend to wake up.
//   • Search-engine bots → generous timeout (8s) so they ALWAYS get the full
//     SSR HTML and indexing/SEO is never affected.
// -----------------------------------------------------------------------------

export const config = { matcher: '/' };

const SSR_ORIGIN = 'https://quienva.onrender.com/api/home';

const BOT_RE = /(googlebot|bingbot|slurp|duckduckbot|baiduspider|yandex|sogou|exabot|facebot|facebookexternalhit|twitterbot|linkedinbot|whatsapp|telegrambot|applebot|petalbot|ia_archiver|semrushbot|ahrefsbot|discordbot|pinterest|embedly|redditbot)/i;

export default async function middleware(request) {
  try {
    const method = request.method || 'GET';
    // Only intercept top-level page loads. Anything else -> normal SPA.
    if (method !== 'GET' && method !== 'HEAD') return;

    const ua = request.headers.get('user-agent') || '';
    const isBot = BOT_RE.test(ua);
    // Bots wait for the full SSR (SEO); humans never wait on a cold backend.
    const timeoutMs = isBot ? 8000 : 1500;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let res;
    try {
      res = await fetch(SSR_ORIGIN, {
        method: 'GET',
        headers: {
          // Force the canonical public host so the SSR canonical/hreflang/og URLs
          // stay on www.quienva.me (not the Render origin).
          'x-forwarded-host': 'www.quienva.me',
          'x-forwarded-proto': 'https',
          'user-agent': ua,
          'accept-language': request.headers.get('accept-language') || '',
        },
        redirect: 'manual',
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) return; // SSR unavailable -> serve SPA (safe fallback)

    const ctype = res.headers.get('content-type') || '';
    if (!ctype.includes('text/html')) return; // unexpected -> serve SPA

    const html = await res.text();
    if (!html || html.length < 200) return; // sanity check -> serve SPA

    return new Response(html, {
      status: 200,
      headers: {
        'content-type': 'text/html; charset=utf-8',
        // Edge-cache the SSR homepage so it is instant for most visitors while
        // staying fresh (revalidated hourly, stale served up to a day).
        'cache-control': 'public, max-age=0, s-maxage=3600, stale-while-revalidate=86400',
        'x-qv-home': isBot ? 'ssr-bot' : 'ssr',
      },
    });
  } catch (e) {
    return; // any failure (incl. timeout/abort) -> serve the normal SPA
  }
}
