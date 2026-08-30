// Native push (APNs) registration for the iOS App Store app via Capacitor.
// On the web this file is never used (guarded by isNativeApp()).
import api from "@/lib/api";
import { isNativeApp } from "@/lib/platform";

let listenersReady = false;

// Best-effort diagnostic reporter: tells the SERVER what happens on the device
// (permission result, APNs token arrival, upload ok/failed with the exact error)
// so we can diagnose push without Xcode. Never throws.
async function reportDebug(stage, extra = {}) {
  try {
    let email = null;
    try {
      email = JSON.parse(localStorage.getItem("qv_user") || "null")?.email || null;
    } catch {
      /* ignore */
    }
    const logged_in = !!localStorage.getItem("qv_token");
    await api.post("/push/apns/debug", { stage, platform: "ios", email, logged_in, ...extra });
  } catch (e) {
    /* ignore: diagnostics must never break the app */
  }
}

async function ensureListeners(PushNotifications) {
  if (listenersReady) return;
  listenersReady = true;
  // When iOS returns the APNs device token, send it to the backend.
  await PushNotifications.addListener("registration", async (token) => {
    const token_prefix = (token?.value || "").slice(0, 14);
    await reportDebug("registration_event", { token_prefix });
    try {
      await api.post("/push/apns/register", { token: token.value });
      await reportDebug("upload_ok", { token_prefix });
    } catch (e) {
      const status = e?.response?.status;
      await reportDebug("upload_failed", {
        token_prefix,
        detail: `status=${status ?? "n/a"} ${e?.message || ""}`,
      });
      // Non-fatal: the in-app notifications still work.
      console.error("APNs token upload failed", e);
    }
  });
  await PushNotifications.addListener("registrationError", (err) => {
    reportDebug("registration_error", {
      detail: (err && (err.error || err.message)) || JSON.stringify(err || {}),
    });
    console.error("APNs registration error", err);
  });
}

// Ask permission + register with APNs. Throws Error('denied') if the user says no.
export async function registerNativePush() {
  if (!isNativeApp()) return false;
  const { PushNotifications } = await import("@capacitor/push-notifications");
  const perm = await PushNotifications.requestPermissions();
  await reportDebug("request_permissions", { detail: `receive=${perm?.receive}` });
  if (perm.receive !== "granted") {
    const err = new Error("Permiso de notificaciones denegado.");
    err.code = "denied";
    throw err;
  }
  await ensureListeners(PushNotifications);
  await PushNotifications.register();
  await reportDebug("register_called", {});
  return true;
}

// Best-effort: attach tap handler so opening a push navigates in-app.
export async function attachNativePushTapHandler(onNavigate) {
  if (!isNativeApp()) return;
  try {
    const { PushNotifications } = await import("@capacitor/push-notifications");
    await PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
      const url = action?.notification?.data?.url;
      if (url && typeof onNavigate === "function") onNavigate(url);
    });
  } catch {
    /* ignore */
  }
}

// Called on every app start (native): if the user already granted permission,
// silently re-register so the current APNs device token is (re)sent to the
// backend. Tokens can rotate and the very first upload may have failed, which
// is a common reason pushes stop arriving.
export async function refreshNativePushIfGranted() {
  if (!isNativeApp()) return;
  try {
    const { PushNotifications } = await import("@capacitor/push-notifications");
    const perm = await PushNotifications.checkPermissions();
    await reportDebug("app_start_check", { detail: `receive=${perm?.receive}` });
    if (perm.receive === "granted") {
      await ensureListeners(PushNotifications);
      await PushNotifications.register();
      await reportDebug("register_called", { detail: "from app_start" });
    } else if (perm.receive === "prompt" || perm.receive === "prompt-with-rationale") {
      // Undetermined (e.g. an existing user who skips onboarding on a fresh
      // install): ask now so the token still gets registered.
      const asked = await PushNotifications.requestPermissions();
      await reportDebug("app_start_request", { detail: `receive=${asked?.receive}` });
      if (asked.receive === "granted") {
        await ensureListeners(PushNotifications);
        await PushNotifications.register();
        await reportDebug("register_called", { detail: "from app_start_request" });
      }
    }
  } catch (e) {
    reportDebug("app_start_error", { detail: e?.message || String(e) });
    console.error("refreshNativePush failed", e);
  }
}
