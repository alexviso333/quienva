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
