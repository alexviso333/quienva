// Live Activity (Dynamic Island) del "⚡ EL MOMENTO" — solo app nativa iOS.
// Plugin nativo: /app/frontend/native/LiveActivity/QuienVaMomentLiveActivityPlugin.swift
// Mismo patrón que lib/liveActivity.js (plan), pero para capturas de Momento.
// En web/Android todo esto es un no-op silencioso.
import { registerPlugin, Capacitor } from "@capacitor/core";
import api from "@/lib/api";
import { isNativeApp } from "@/lib/platform";

const MomentLA = registerPlugin("QuienVaMomentLiveActivity");

let listenerBound = false;
const started = new Set();         // eventIds con LA ya arrancada en esta sesión

function available() {
  return isNativeApp()
    && Capacitor.getPlatform() === "ios"
    && Capacitor.isPluginAvailable("QuienVaMomentLiveActivity");
}

function bindTokenListener() {
  if (listenerBound || !available()) return;
  listenerBound = true;
  // El per-activity push token se envia al backend para que pueda terminar
  // la Live Activity remotamente al parar el Momento (`_fire_moment_live_end`).
  MomentLA.addListener("momentToken", async ({ eventId, token }) => {
    try {
      await api.post("/live-activity/token", {
        activity_id: `moment:${eventId}`,
        token,
        event_id: eventId,
      });
    } catch (e) { /* ignore */ }
  });
}

function epochOf(iso) {
  if (!iso) return undefined;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t / 1000 : undefined;
}

/** Arranca la Live Activity del Momento. Llama en cuanto `/me/active-moment`
 * devuelve `active:true` y el usuario sigue en la app. Idempotente. */
export async function startMomentActivity(moment) {
  if (!available() || !moment?.event_id) return;
  if (started.has(moment.event_id)) return;
  started.add(moment.event_id);
  bindTokenListener();
  try {
    await MomentLA.startMoment({
      eventId: moment.event_id,
      ciudad: moment.city || "",
      fase: "momento",
      deadlineEpoch: epochOf(moment?.prompt?.on_time_deadline),
      nombreEvento: moment.event_name || "",
      subiendoAhora: moment.capturing_now ?? 0,
      amigosDentro: moment.friends_captured ?? 0,
      misLikes: 0,
    });
  } catch (e) {
    started.delete(moment.event_id);
  }
}

/** Actualiza la LA (nº subiendo ahora, fase captured, likes). */
export async function updateMomentActivity(moment, overrides = {}) {
  if (!available() || !moment?.event_id || !started.has(moment.event_id)) return;
  try {
    await MomentLA.updateMoment({
      eventId: moment.event_id,
      fase: overrides.fase ?? "momento",
      deadlineEpoch: epochOf(moment?.prompt?.on_time_deadline),
      nombreEvento: moment.event_name || "",
      subiendoAhora: overrides.subiendoAhora ?? moment.capturing_now ?? 0,
      amigosDentro: overrides.amigosDentro ?? moment.friends_captured ?? 0,
      misLikes: overrides.misLikes ?? 0,
    });
  } catch (e) { /* ignore */ }
}

/** Termina la LA (dismiss en 5 min del lockscreen). */
export async function endMomentActivity(eventId) {
  if (!available() || !eventId || !started.has(eventId)) return;
  started.delete(eventId);
  try {
    await MomentLA.endMoment({ eventId });
    await api.post("/live-activity/end", { activity_id: `moment:${eventId}` });
  } catch (e) { /* ignore */ }
}
