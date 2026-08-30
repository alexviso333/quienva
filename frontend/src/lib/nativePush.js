// Native push (APNs) registration for the iOS App Store app via Capacitor.
// On the web this file is never used (guarded by isNativeApp()).
import api from "@/lib/api";
import { isNativeApp } from "@/lib/platform";

let listenersReady = false;

async function ensureListeners(PushNotifications) {
  if (listenersReady) return;
  listenersReady = true;
  // When iOS returns the APNs device token, send it to the backend.
  await PushNotifications.addListener("registration", async (token) => {
    try {
      await api.post("/push/apns/register", { token: token.value });
    } catch (e) {
      // Non-fatal: the in-app notifications still work.
      console.error("APNs token upload failed", e);
    }
  });
  await PushNotifications.addListener("registrationError", (err) => {
    console.error("APNs registration error", err);
  });
}

// Ask permission + register with APNs. Throws Error('denied') if the user says no.
export async function registerNativePush() {
  if (!isNativeApp()) return false;
  const { PushNotifications } = await import("@capacitor/push-notifications");
  const perm = await PushNotifications.requestPermissions();
  if (perm.receive !== "granted") {
    const err = new Error("Permiso de notificaciones denegado.");
    err.code = "denied";
    throw err;
  }
  await ensureListeners(PushNotifications);
  await PushNotifications.register();
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
    if (perm.receive === "granted") {
      await ensureListeners(PushNotifications);
      await PushNotifications.register();
    }
  } catch (e) {
    console.error("refreshNativePush failed", e);
  }
}
