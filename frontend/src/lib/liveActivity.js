// Live Activity (Dynamic Island) del plan — solo app nativa iOS.
// El plugin nativo vive en frontend/native/LiveActivity/ y Codemagic lo compila
// como extensión de widget. En web/Android todo esto es un no-op silencioso.
import { registerPlugin, Capacitor } from "@capacitor/core";
import api from "@/lib/api";
import { isNativeApp } from "@/lib/platform";

const LiveActivity = registerPlugin("QuienVaLiveActivity");

let listenerBound = false;
const started = new Set();

function available() {
  return isNativeApp() && Capacitor.getPlatform() === "ios" && Capacitor.isPluginAvailable("QuienVaLiveActivity");
}

function bindTokenListener() {
  if (listenerBound || !available()) return;
  listenerBound = true;
  // Cada actividad tiene su propio token de APNs: lo mandamos al backend para
  // que pueda actualizar la isla en vivo cuando alguien vota.
  LiveActivity.addListener("planToken", async ({ slug, token }) => {
    try {
      await api.post("/live-activity/token", { activity_id: `plan:${slug}`, token, plan_slug: slug });
    } catch (e) { /* ignore */ }
  });
}

function epochOf(iso) {
  if (!iso) return undefined;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t / 1000 : undefined;
}

export async function startPlanActivity(plan) {
  if (!available() || !plan?.slug || plan.estado !== "abierto") return;
  if (started.has(plan.slug)) return;
  started.add(plan.slug);
  bindTokenListener();
  try {
    await LiveActivity.startPlan({
      slug: plan.slug,
      titulo: plan.titulo || "Tu plan",
      ciudad: plan.ciudad || "",
      dentro: plan.counts?.dentro ?? 0,
      umbral: plan.umbral_personas ?? 0,
      cierraEpoch: epochOf(plan.hora_limite),
      estado: plan.estado,
    });
  } catch (e) {
    started.delete(plan.slug);
  }
}

export async function updatePlanActivity(plan) {
  if (!available() || !plan?.slug || !started.has(plan.slug)) return;
  try {
    await LiveActivity.updatePlan({
      slug: plan.slug,
      dentro: plan.counts?.dentro ?? 0,
      umbral: plan.umbral_personas ?? 0,
      cierraEpoch: epochOf(plan.hora_limite),
      ganadora: plan.opcion_ganadora_nombre || undefined,
      estado: plan.estado,
    });
  } catch (e) { /* ignore */ }
}

export async function endPlanActivity(slug) {
  if (!available() || !slug || !started.has(slug)) return;
  started.delete(slug);
  try {
    await LiveActivity.endPlan({ slug });
    await api.post("/live-activity/end", { activity_id: `plan:${slug}` });
  } catch (e) { /* ignore */ }
}
