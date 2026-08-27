import { Capacitor } from "@capacitor/core";
import api from "@/lib/api";

// "Iniciar sesión con Apple" is required by App Store guideline 4.8 whenever a
// third-party login (Google) is offered. We show it ONLY inside the native iOS
// app; the web keeps Google. The native plugin is imported lazily so the web
// bundle never depends on the native module.
export function isAppleSignInAvailable() {
  try {
    return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "ios";
  } catch (e) {
    return false;
  }
}

// Returns true when the thrown error is just the user cancelling the sheet.
export function isAppleCancel(err) {
  const msg = String(err?.message || err?.code || "").toLowerCase();
  return (
    msg.includes("1001") || // ASAuthorizationError.canceled
    msg.includes("cancel") ||
    msg.includes("the operation couldn")
  );
}

export async function startAppleLogin() {
  const { SignInWithApple } = await import("@capacitor-community/apple-sign-in");
  const result = await SignInWithApple.authorize({
    // Native iOS uses the app bundle id; redirectURI is unused (no web redirect).
    clientId: "me.quienva.app",
    redirectURI: "",
    scopes: "email name",
  });
  const r = (result && result.response) || {};
  if (!r.identityToken) throw new Error("Apple no devolvió el token de identidad");
  // Apple only sends the name on the FIRST authorization — capture it now.
  const name = [r.givenName, r.familyName].filter(Boolean).join(" ").trim() || null;
  const { data } = await api.post("/auth/apple/callback", {
    identity_token: r.identityToken,
    code: r.authorizationCode || null,
    name,
    email: r.email || null,
  });
  return data; // { user, token }
}
