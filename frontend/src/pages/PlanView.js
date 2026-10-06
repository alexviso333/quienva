import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AppShell } from "@/components/AppShell";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { AvatarCircle } from "@/components/AvatarCircle";
import api, { mediaThumb } from "@/lib/api";
import { toast } from "sonner";
import { captureEvent } from "@/analytics/posthog";
import {
  Loader2, Clock, Users, MapPin, Check, Send, Link2, ArrowLeft, Home, PartyPopper, X,
} from "lucide-react";

const INTENTS = [
  { key: "dentro", emoji: "🟢", labelKey: "planview.in", label: "Yo voy", style: "primary" },
  { key: "voy_si", emoji: "🟡", labelKey: "planview.maybe", label: "Voy si somos +", style: "secondary" },
  { key: "depende", emoji: "🟠", labelKey: "planview.depends", label: "Depende", style: "ghost" },
  { key: "paso", emoji: "⚫", labelKey: "planview.out", label: "Paso", style: "link" },
];

function ctFor(slug) { try { return localStorage.getItem(`qv_ct_${slug}`); } catch (e) { return null; } }
function ptFor(slug) { try { return localStorage.getItem(`qv_pt_${slug}`); } catch (e) { return null; } }

export default function PlanView() {
  const { slug } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [respondFor, setRespondFor] = useState(null); // intencion key being confirmed
  const [apodo, setApodo] = useState(() => { try { return localStorage.getItem("qv_apodo") || ""; } catch (e) { return ""; } });
  const [telefono, setTelefono] = useState("");
  const [prefOpt, setPrefOpt] = useState(null);

  const pt = ptFor(slug);
  const ct = ctFor(slug);

  const { data: plan, isLoading, isError } = useQuery({
    queryKey: ["plan", slug],
    queryFn: async () => (await api.get(`/plans/${slug}`, { headers: pt ? { "x-participante-token": pt } : {} })).data,
    enabled: !!slug,
    staleTime: 10000,
    refetchInterval: 15000,
  });

  const counts = plan?.counts || {};
  const options = plan?.opciones || [];
  const isClosed = plan && plan.estado !== "abierto";
  const isCreator = !!(plan?.is_creator || ct);

  const respondMut = useMutation({
    mutationFn: async (intencion) => {
      const body = { apodo: apodo.trim(), intencion, telefono: telefono.trim() || undefined, opcion_preferida: prefOpt || undefined, participante_token: pt || undefined };
      return (await api.post(`/plans/${slug}/respond`, body)).data;
    },
    onSuccess: (data, intencion) => {
      try { if (data?.participante_token) localStorage.setItem(`qv_pt_${slug}`, data.participante_token); localStorage.setItem("qv_apodo", apodo.trim()); } catch (e) { /* ignore */ }
      captureEvent("plan_response_submitted", { plan_id: slug, intencion, opcion_preferida: prefOpt || null });
      qc.setQueryData(["plan", slug], data.plan);
      setRespondFor(null);
      toast.success(t("planview.saved", "¡Respuesta guardada!"));
    },
    onError: (e) => toast.error(e?.response?.data?.detail || t("planview.error", "No se pudo guardar")),
  });

  const closeMut = useMutation({
    mutationFn: async (action) => (await api.post(`/plans/${slug}/${action}`, {}, { headers: ct ? { "x-participante-token": ct } : {} })).data,
    onSuccess: (data) => { if (data?.plan) qc.setQueryData(["plan", slug], data.plan); toast.success(t("planview.updated", "Plan actualizado")); },
    onError: (e) => toast.error(e?.response?.data?.detail || t("planview.error", "No se pudo")),
  });

  const fecha = useMemo(() => {
    if (!plan?.fecha_objetivo) return null;
    try {
      const d = new Date(plan.fecha_objetivo);
      return d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
    } catch (e) { return null; }
  }, [plan]);

  const closesLabel = useMemo(() => {
    if (!plan?.hora_limite) return null;
    try { const d = new Date(plan.hora_limite); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; } catch (e) { return null; }
  }, [plan]);

  const shareText = plan ? `👀 ${plan.titulo || "¿Quién va?"} — dinos si te apuntas` : "";
  const shareUrl = typeof window !== "undefined" ? window.location.href : "";
  const shareWhatsApp = () => { captureEvent("plan_shared", { plan_id: slug, destination: "whatsapp" }); window.open(`https://wa.me/?text=${encodeURIComponent(`${shareText}: ${shareUrl}`)}`, "_blank", "noopener,noreferrer"); };
  const copyLink = async () => { captureEvent("plan_shared", { plan_id: slug, destination: "copy_link" }); try { await navigator.clipboard.writeText(shareUrl); toast.success(t("planview.copied", "Enlace copiado")); } catch (e) { /* ignore */ } };

  const dentro = counts.dentro || 0;
  const pct = plan?.umbral_personas ? Math.min(100, Math.round((dentro / plan.umbral_personas) * 100)) : null;

  const btnClass = (style, active) => {
    if (active) return "bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]";
    if (style === "primary") return "bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]";
    if (style === "secondary") return "bg-white/[0.06] border border-qv-primary/40 text-white";
    if (style === "ghost") return "bg-white/[0.06] border border-white/12 text-white/80";
    return "bg-transparent text-white/50";
  };

  return (
    <AppShell>
      <div className="min-h-screen pb-28">
        {/* Top bar inside the app */}
        <div className="flex items-center justify-between px-4 pt-5 pb-2">
          <button onClick={() => navigate(-1)} data-testid="planview-back" className="inline-flex items-center gap-1.5 text-sm font-bold text-white/70 bg-white/[0.06] border border-white/10 rounded-full px-3 py-1.5 active:scale-95">
            <ArrowLeft className="w-4 h-4" /> {t("planview.back", "Volver")}
          </button>
          <button onClick={() => navigate("/feed")} data-testid="planview-home" className="inline-flex items-center gap-1.5 text-sm font-black text-qv-primary active:scale-95">
            <Home className="w-4 h-4" /> ¿Quién va?
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-24"><Loader2 className="w-7 h-7 text-qv-primary animate-spin" /></div>
        ) : isError || !plan ? (
          <div className="text-center py-24 px-6">
            <PartyPopper className="w-10 h-10 text-white/30 mx-auto mb-3" />
            <p className="text-white/70">{t("planview.not_found", "Este plan ya no está disponible")}</p>
            <button onClick={() => navigate("/feed")} className="mt-4 text-sm font-bold text-qv-primary">{t("planview.explore", "Explorar fiestas")}</button>
          </div>
        ) : (
          <div className="px-4" data-testid="planview">
            {/* Header */}
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-qv-secondary">{plan.ciudad}{fecha ? ` · ${fecha}` : ""}</p>
            <h1 className="font-display text-3xl font-black text-white leading-tight mt-1">{plan.titulo || t("planview.default_title", "¿Nos cuadra este plan?")}</h1>
            {plan.mensaje_creador ? (
              <div className="mt-3 flex items-start gap-2.5 bg-white/[0.04] border border-white/10 rounded-2xl p-3">
                <AvatarCircle name={plan.creador_apodo || "?"} size={32} />
                <p className="text-sm text-white/85 leading-snug"><b>{plan.creador_apodo || "Alguien"}:</b> {plan.mensaje_creador}</p>
              </div>
            ) : null}

            {/* Status */}
            {isClosed ? (
              <div className="mt-4 rounded-2xl border border-qv-primary/40 bg-qv-primary/10 p-3.5 text-center" data-testid="planview-closed">
                <p className="font-bold text-white">{plan.estado === "cancelado" ? t("planview.cancelled", "Plan cancelado") : t("planview.closed", "Plan cerrado")}</p>
                {plan.estado === "cerrado" && plan.opcion_ganadora ? (
                  <p className="text-sm text-white/70 mt-0.5">{t("planview.winner", "Quedáis en {{v}}", { v: (options.find((o) => o.opt_id === plan.opcion_ganadora)?.venue_nombre) || "el sitio elegido" })}</p>
                ) : null}
              </div>
            ) : null}

            {/* Options */}
            <div className="mt-4 flex flex-col gap-2.5">
              {options.map((o) => {
                const chosen = prefOpt === o.opt_id || plan.opcion_ganadora === o.opt_id;
                return (
                  <button
                    key={o.opt_id}
                    data-testid={`planview-option-${o.opt_id}`}
                    onClick={() => { if (!isClosed && options.length > 1) setPrefOpt((p) => (p === o.opt_id ? null : o.opt_id)); }}
                    className={`flex items-center gap-3 rounded-2xl border p-2.5 text-left transition-colors ${chosen ? "border-qv-primary/60 bg-qv-primary/10" : "border-white/10 bg-white/[0.03]"}`}
                  >
                    {o.image_url ? <img src={mediaThumb(o.image_url, 160)} alt="" className="w-14 h-14 rounded-xl object-cover shrink-0" /> : <div className="w-14 h-14 rounded-xl bg-white/5 flex items-center justify-center shrink-0"><MapPin className="w-5 h-5 text-white/40" /></div>}
                    <div className="min-w-0 flex-1">
                      <p className="font-bold text-white text-sm truncate">{o.venue_nombre || o.texto_libre}</p>
                      <p className="text-xs text-white/55 truncate">{[o.hora, o.precio_desde ? `desde ${Math.round(o.precio_desde)}€` : null].filter(Boolean).join(" · ") || "\u00a0"}</p>
                    </div>
                    {chosen ? <Check className="w-5 h-5 text-qv-primary shrink-0" /> : (options.length > 1 && !isClosed ? <span className="text-[10px] text-white/40 shrink-0">{t("planview.prefer", "Prefiero")}</span> : null)}
                  </button>
                );
              })}
            </div>

            {/* Progress */}
            {plan.umbral_personas ? (
              <div className="mt-4" data-testid="planview-progress">
                <div className="flex items-center justify-between text-xs text-white/70 mb-1.5">
                  <span className="flex items-center gap-1 font-semibold"><Users className="w-3.5 h-3.5" /> {dentro}/{plan.umbral_personas} {t("planview.inside", "dentro")}</span>
                  {closesLabel ? <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {t("planview.closes", "cierra {{t}}", { t: closesLabel })}</span> : null}
                </div>
                <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-qv-primary to-[#8b5cf6] rounded-full transition-all" style={{ width: `${pct}%` }} />
                </div>
              </div>
            ) : null}

            {/* Participants */}
            {(plan.participants || []).length > 0 && (
              <div className="mt-4" data-testid="planview-participants">
                <p className="text-xs font-bold uppercase tracking-wider text-white/50 mb-2">{t("planview.who", "Quién responde")} ({plan.participants.length})</p>
                <div className="flex flex-col gap-1.5">
                  {plan.participants.map((p, i) => (
                    <div key={i} className="flex items-center gap-2.5 text-sm">
                      <AvatarCircle name={p.apodo} size={26} />
                      <span className="text-white/85 flex-1 truncate">{p.apodo}</span>
                      <span>{p.emoji}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Your response status */}
            {plan.mine && !isClosed ? (
              <div className="mt-4 rounded-2xl border border-white/12 bg-white/[0.04] p-3 flex items-center justify-between" data-testid="planview-mine">
                <p className="text-sm text-white/85">{t("planview.your_answer", "Tu respuesta")}: <b>{INTENTS.find((x) => x.key === plan.mine.intencion)?.emoji} {t(INTENTS.find((x) => x.key === plan.mine.intencion)?.labelKey, INTENTS.find((x) => x.key === plan.mine.intencion)?.label)}</b></p>
                <button onClick={() => setRespondFor(plan.mine.intencion)} className="text-xs font-bold text-qv-primary">{t("planview.change", "Cambiar")}</button>
              </div>
            ) : null}

            {/* Share */}
            <div className="mt-5 grid grid-cols-2 gap-2">
              <button onClick={shareWhatsApp} data-testid="planview-share-wa" className="bg-white/[0.06] border border-white/12 text-white/85 rounded-2xl py-2.5 font-semibold text-sm flex items-center justify-center gap-1.5 active:scale-[0.99]">
                <Send className="w-4 h-4 text-[#25D366]" /> {t("planview.share", "Compartir")}
              </button>
              <button onClick={copyLink} className="bg-white/[0.06] border border-white/12 text-white/85 rounded-2xl py-2.5 font-semibold text-sm flex items-center justify-center gap-1.5 active:scale-[0.99]">
                <Link2 className="w-4 h-4" /> {t("planview.copy", "Copiar enlace")}
              </button>
            </div>

            {/* Creator controls */}
            {isCreator && !isClosed ? (
              <div className="mt-3 flex items-center justify-center gap-4 text-xs" data-testid="planview-creator">
                <button onClick={() => closeMut.mutate("close")} className="text-white/60 font-semibold active:scale-95">{t("planview.close_now", "Cerrar plan ahora")}</button>
                <span className="text-white/20">·</span>
                <button onClick={() => closeMut.mutate("cancel")} className="text-white/40 active:scale-95">{t("planview.cancel_plan", "Cancelar")}</button>
              </div>
            ) : null}
          </div>
        )}

        {/* Sticky response bar */}
        {plan && !isClosed && !plan.mine && (
          <div className="fixed bottom-[70px] left-0 right-0 z-20 px-4" data-testid="planview-respond-bar">
            <div className="mx-auto max-w-md bg-[#120d18]/95 backdrop-blur-md border border-white/12 rounded-2xl p-2 grid grid-cols-2 gap-2 shadow-2xl">
              {INTENTS.map((it) => (
                <button
                  key={it.key}
                  data-testid={`planview-intent-${it.key}`}
                  onClick={() => setRespondFor(it.key)}
                  className={`h-11 rounded-xl font-bold text-sm flex items-center justify-center gap-1.5 active:scale-[0.98] ${btnClass(it.style, false)}`}
                >
                  <span>{it.emoji}</span> {t(it.labelKey, it.label)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Minimal response drawer (no account needed) */}
      <Drawer open={!!respondFor} onOpenChange={(o) => { if (!o) setRespondFor(null); }}>
        <DrawerContent className="bg-[#120d18] border-t border-white/10 text-white focus:outline-none" data-testid="planview-respond-sheet">
          <div className="mx-auto w-full max-w-md px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-2">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display font-black text-lg">{INTENTS.find((x) => x.key === respondFor)?.emoji} {t(INTENTS.find((x) => x.key === respondFor)?.labelKey, INTENTS.find((x) => x.key === respondFor)?.label)}</h2>
              <button onClick={() => setRespondFor(null)} className="text-white/40 active:scale-90"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-white/45 text-[11px] mb-1">{t("planview.your_name", "¿Cómo te llaman?")}</p>
            <input value={apodo} onChange={(e) => setApodo(e.target.value)} maxLength={40} placeholder={t("planview.name_ph", "Alex")} autoFocus
              className="w-full bg-[#0a0712] border border-white/12 rounded-xl px-3 py-3 text-sm outline-none focus:border-qv-primary/50" />
            <p className="text-white/45 text-[11px] mt-3 mb-1">{t("planview.phone_opt", "Teléfono para avisarte si se cierra (opcional)")}</p>
            <input value={telefono} onChange={(e) => setTelefono(e.target.value)} inputMode="tel" placeholder="+34..."
              className="w-full bg-[#0a0712] border border-white/12 rounded-xl px-3 py-3 text-sm outline-none focus:border-qv-primary/50" />
            <button
              onClick={() => { if (!apodo.trim()) { toast.error(t("planview.need_name", "Dinos cómo te llaman")); return; } respondMut.mutate(respondFor); }}
              disabled={respondMut.isPending}
              data-testid="planview-confirm"
              className="w-full mt-4 bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white rounded-2xl py-3.5 font-bold text-[15px] flex items-center justify-center gap-2 disabled:opacity-60 active:scale-[0.99]"
            >
              {respondMut.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Check className="w-4 h-4" />} {t("planview.confirm", "Confirmar")}
            </button>
          </div>
        </DrawerContent>
      </Drawer>
    </AppShell>
  );
}
