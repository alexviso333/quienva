// Live Activity (Dynamic Island) del plan — solo app nativa iOS.
// El plugin nativo vive en frontend/native/LiveActivity/ y Codemagic lo compila
// como extensión de widget. En web/Android todo esto es un no-op silencioso.
import { registerPlugin, Capacitor } from "@capacitor/core";
import api from "@/lib/api";
import { isNativeApp } from "@/lib/platform";

const LiveActivity = registerPlugin("QuienVaLiveActivity");

let listenerBound = false;
const started = new Set();
const lastLugar = new Map();   // slug -> último sitio ganador conocido

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

// Opción que va ganando la votación — igual que _plan_leading_option en el
// backend, para que la isla arranque ya con el dato sin esperar a un push.
function leadingOf(plan) {
  const opts = plan?.opciones || [];
  const nombre = (o) => (o?.venue_nombre || o?.texto_libre || "").trim().slice(0, 28);
  if (!opts.length) return { lugar: undefined, lugarVotos: 0, numOpciones: 0 };
  if (opts.length === 1) return { lugar: nombre(opts[0]) || undefined, lugarVotos: 0, numOpciones: 1 };
  const tally = {};
  (plan.participants || []).forEach((p) => {
    if ((p.intencion === "dentro" || p.intencion === "voy_si") && p.opcion_preferida) {
      tally[p.opcion_preferida] = (tally[p.opcion_preferida] || 0) + 1;
    }
  });
  const best = Object.entries(tally).sort((a, b) => b[1] - a[1])[0];
  const opt = best ? opts.find((o) => o.opt_id === best[0]) : opts[0];
  return { lugar: nombre(opt || opts[0]) || undefined, lugarVotos: best ? best[1] : 0, numOpciones: opts.length };
}

export async function startPlanActivity(plan) {
  if (!available() || !plan?.slug || plan.estado !== "abierto") return;
  if (started.has(plan.slug)) return;
  started.add(plan.slug);
  bindTokenListener();
  const lead = leadingOf(plan);
  if (lead.lugar) lastLugar.set(plan.slug, lead.lugar);
  try {
    await LiveActivity.startPlan({
      slug: plan.slug,
      titulo: plan.titulo || "Tu plan",
      ciudad: plan.ciudad || "",
      dentro: plan.counts?.dentro ?? 0,
      umbral: plan.umbral_personas ?? 0,
      cierraEpoch: epochOf(plan.hora_limite),
      estado: plan.estado,
      ...lead,
    });
  } catch (e) {
    started.delete(plan.slug);
  }
}

export async function updatePlanActivity(plan) {
  if (!available() || !plan?.slug || !started.has(plan.slug)) return;
  const lead = leadingOf(plan);
  // Si cambia el sitio que va ganando, la actualización va con alerta: iOS
  // vibra y destaca la isla dinámica en vez de cambiarla en silencio.
  const prev = lastLugar.get(plan.slug);
  const changed = lead.numOpciones > 1 && lead.lugar && prev && lead.lugar !== prev;
  if (lead.lugar) lastLugar.set(plan.slug, lead.lugar);
  try {
    await LiveActivity.updatePlan({
      slug: plan.slug,
      dentro: plan.counts?.dentro ?? 0,
      umbral: plan.umbral_personas ?? 0,
      cierraEpoch: epochOf(plan.hora_limite),
      ganadora: plan.opcion_ganadora_nombre || undefined,
      estado: plan.estado,
      ...lead,
      cambio: changed || undefined,
      alertTitle: changed ? "¡Cambio de plan!" : undefined,
      alertBody: changed ? `Ahora va ganando ${lead.lugar}` : undefined,
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
