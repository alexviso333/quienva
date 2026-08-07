import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Kick off the Google OAuth (authorization-code) flow.
 *
 * Reused by the login screen AND the guest registration modal so a visitor can
 * sign up in one tap. Reads the public config from the backend; if Google isn't
 * configured (e.g. local dev without credentials) it shows a friendly toast
 * instead of a broken redirect. On success it navigates the browser to Google;
 * any pending invite (?add=) / referral (?ref=) already stored in localStorage
 * survives the round-trip and is applied after the callback sets the session.
 */
export async function startGoogleLogin() {
  try {
    const { data } = await api.get("/auth/google/config");
    if (!data.enabled || !data.client_id) {
      toast.error("Google no está disponible ahora mismo. Usa tu email para entrar.");
      return false;
    }
    const redirectUri = window.location.origin + "/auth/callback";
    const params = new URLSearchParams({
      client_id: data.client_id,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: "openid email profile",
      access_type: "online",
      prompt: "select_account",
    });
    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
    return true;
  } catch (e) {
    toast.error("No se pudo iniciar Google. Inténtalo de nuevo.");
    return false;
  }
}
