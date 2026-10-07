// Enlaces PÚBLICOS para compartir.
//
// PROBLEMA: dentro de la app nativa (Capacitor) `window.location.origin` es
// `capacitor://localhost` o `https://localhost`. Si construyes el link de
// WhatsApp con eso, a quien lo recibe le llega "capacitor://localhost/p/xxx",
// que no abre nada.
//
// SOLUCIÓN: todo lo que se comparte fuera de la app se construye SIEMPRE sobre
// el dominio público. En web es el mismo dominio, así que no cambia nada.
const FALLBACK = "https://www.quienva.me";

export const PUBLIC_BASE = (
  process.env.REACT_APP_PUBLIC_WEB_URL || FALLBACK
).replace(/\/$/, "");

/** URL pública absoluta para un path de la app ("/p/abc" -> "https://www.quienva.me/p/abc"). */
export function publicUrl(path = "/") {
  const p = String(path || "/");
  return `${PUBLIC_BASE}${p.startsWith("/") ? p : `/${p}`}`;
}

/**
 * Normaliza una URL que venga del backend: si por configuración trae un host
 * local / de preview / de capacitor, la reescribe al dominio público.
 */
export function ensurePublicUrl(url, fallbackPath = "/") {
  if (!url) return publicUrl(fallbackPath);
  try {
    const u = new URL(url);
    const bad = u.protocol === "capacitor:"
      || u.hostname === "localhost"
      || u.hostname === "127.0.0.1"
      || u.hostname.endsWith(".local");
    if (bad) return publicUrl(`${u.pathname}${u.search}`);
    return url;
  } catch {
    return publicUrl(url.startsWith("/") ? url : fallbackPath);
  }
}
