import posthog from "posthog-js";

const token = process.env.REACT_APP_POSTHOG_PROJECT_TOKEN;
const host = process.env.REACT_APP_POSTHOG_HOST || "https://eu.i.posthog.com";

let enabled = false;

export function initAnalytics() {
  if (enabled) return;
  if (!token) {
    // Fail safe: analytics disabled when no project token configured.
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
  } catch (e) {
    // never let analytics break the app
    // eslint-disable-next-line no-console
    console.warn("PostHog init failed");
  }
}

export function captureEvent(eventName, properties = {}) {
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
