import api from "@/lib/api";
import { toast } from "sonner";
import { isNativeApp } from "@/lib/platform";

// Custom URL scheme the web callback uses to hand the session back to the app.
// Registered in Info.plist by the Codemagic build (CFBundleURLSchemes).
export const APP_URL_SCHEME = "quienva";

/**
 * Kick off the Google OAuth (authorization-code) flow.
 *
 * WEB: redirects the browser to Google as before (works in Safari/desktop).
 * NATIVE iOS app: Google BLOCKS its consent screen inside a WebView
 * ("disallowed_useragent"), so we open it in the SYSTEM browser
 * (SFSafariViewController). Google returns to our web callback on the real web
 * origin (quienva.me/auth/callback), which then deep-links the session token
 * back into the app via `quienva://auth-callback?token=...`.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
export async function startGoogleLogin() {
  try {
    const { data } = await api.get("/auth/google/config");
    if (!data.enabled || !data.client_id) {
      toast.error("Google no está disponible ahora mismo. Usa tu email para entrar.");
      return false;
    }

    const native = isNativeApp();
    // WEB: use the current origin. NATIVE: use the canonical web origin from the
    // backend (window.location.origin is https://localhost inside the app).
    const base = native ? (data.web_origin || "").replace(/\/$/, "") : window.location.origin;
    const redirectUri = base + "/auth/callback";

    const params = new URLSearchParams({
      client_id: data.client_id,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: "openid email profile",
      access_type: "online",
      prompt: "select_account",
    });
    // Tell the web callback (running in Safari) to bounce the session back to
    // the app instead of navigating in-page.
    if (native) params.set("state", "native");

    const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;

    if (native) {
      const { Browser } = await import("@capacitor/browser");
      await Browser.open({ url: authUrl, presentationStyle: "popover" });
      return true;
    }

    window.location.href = authUrl;
    return true;
  } catch (e) {
    toast.error("No se pudo iniciar Google. Inténtalo de nuevo.");
    return false;
  }
}
