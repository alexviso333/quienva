import api from "@/lib/api";

function urlB64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function isPushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/service-worker.js");
  } catch (e) {
    return null;
  }
}

export async function getPushStatus() {
  try {
    const { data } = await api.get("/push/status");
    return data.subscribed;
  } catch {
    return false;
  }
}

export async function subscribeToPush() {
  if (!isPushSupported()) throw new Error("Tu navegador no soporta notificaciones push.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Permiso de notificaciones denegado.");

  await registerServiceWorker();
  const reg = await navigator.serviceWorker.ready;
  const { data } = await api.get("/push/vapid-public-key");
  if (!data.publicKey) throw new Error("Push no configurado en el servidor.");

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(data.publicKey),
    });
  }
  await api.post("/push/subscribe", sub.toJSON());
  return true;
}

export async function unsubscribeFromPush() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await api.post("/push/unsubscribe", sub.toJSON());
      await sub.unsubscribe();
    }
  } catch {}
  return false;
}
