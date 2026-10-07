import posthog from "posthog-js";
import api from "@/lib/api";

const token = process.env.REACT_APP_POSTHOG_PROJECT_TOKEN;
const host = process.env.REACT_APP_POSTHOG_HOST || "https://eu.i.posthog.com";

let enabled = false;

export function initAnalytics() {
  if (enabled) return;
  if (!token) {
    // Fail safe: PostHog disabled, pero el mirror al backend sigue funcionando
    // para no perder NINGÚN evento (control absoluto para el admin).
    enabled = false;
    return;
  }
  try {
    posthog.init(token, {
      api_host: host,
      capture_pageview: false, // we capture manually on route change (SPA)
      autocapture: true,
      persistence: "localStorage+cookie",
    });
    enabled = true;
    if (typeof window !== "undefined") window.posthog = posthog;
  } catch (e) {
    // never let analytics break the app
    // eslint-disable-next-line no-console
    console.warn("PostHog init failed");
  }
}

// Fire-and-forget mirror al backend. Nunca bloquea ni rompe la app.
function _mirrorToBackend(eventName, properties = {}) {
  try {
    const payload = {
      event: String(eventName).slice(0, 80),
      props: properties && typeof properties === "object" ? properties : {},
    };
    // navigator.sendBeacon es ideal (no bloquea unload) pero necesita URL
    // absoluta. Usamos api.post directo que ya es no-bloqueante.
    api.post("/track", payload).catch(() => {});
  } catch (e) { /* ignore */ }
}

export function captureEvent(eventName, properties = {}) {
  // Siempre al backend (control total del admin).
  _mirrorToBackend(eventName, properties);
  if (!enabled) return;
  try {
    posthog.capture(eventName, properties);
  } catch (e) {
    /* ignore */
  }
}

export function identifyUser(userId, props = {}) {
  if (!enabled || !userId) return;
  try {
    posthog.identify(String(userId), props);
  } catch (e) {
    /* ignore */
  }
}

export function resetAnalytics() {
  if (!enabled) return;
  try {
    posthog.reset();
  } catch (e) {
    /* ignore */
  }
}

export default posthog;
