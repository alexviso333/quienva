import { useState, useMemo, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { AvatarCircle } from "@/components/AvatarCircle";
import FriendPicker from "@/components/FriendPicker";
import api, { mediaThumb } from "@/lib/api";
import { toast } from "sonner";
import { captureEvent } from "@/analytics/posthog";
import { startPlanActivity, updatePlanActivity, endPlanActivity } from "@/lib/liveActivity";
import {
  Loader2, Clock, Users, MapPin, Check, Send, Link2, ArrowLeft, Home, PartyPopper, X, UserPlus,
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
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [respondFor, setRespondFor] = useState(null); // solo para "cambiar": muestra la barra otra vez
  const [apodo, setApodo] = useState(() => { try { return localStorage.getItem("qv_apodo") || ""; } catch (e) { return ""; } });
  const [prefOpt, setPrefOpt] = useState(null);
  // Nombre: se pide DESPUÉS de votar y es opcional (cero fricción al entrar por el link).
  const [askName, setAskName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [invSel, setInvSel] = useState([]);

  const pt = ptFor(slug);
  const ct = ctFor(slug);

  const { data: plan, isLoading, isError } = useQuery({
    queryKey: ["plan", slug],
    queryFn: async () => (await api.get(`/plans/${slug}`, { headers: pt ? { "x-participante-token": pt } : {} })).data,
    enabled: !!slug,
    staleTime: 10000,
    refetchInterval: 15000,
  });

  useEffect(() => {
    if (slug) captureEvent("plan_viewed", { plan_id: slug });
  }, [slug]);

  const counts = plan?.counts || {};
  // "madrid" (slug) -> "Madrid": el nombre de la ciudad nunca se muestra en minúscula.
  const cityLabel = useMemo(() => {
    const c = (plan?.ciudad || "").replace(/-/g, " ").trim();
    if (!c) return "";
    return c.split(" ").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
  }, [plan]);  const options = plan?.opciones || [];
  const isClosed = plan && plan.estado !== "abierto";
  const isCreator = !!(plan?.is_creator || ct);

  const respondMut = useMutation({
    mutationFn: async ({ intencion, nombre }) => {
      const body = {
        // Si no hay nombre no se bloquea: el servidor usa el de tu cuenta o
        // "Invitado N" y luego se puede cambiar.
        apodo: (nombre !== undefined ? nombre : apodo || "").trim() || undefined,
        intencion,
        opcion_preferida: prefOpt || undefined,
        participante_token: pt || undefined,
      };
      return (await api.post(`/plans/${slug}/respond`, body)).data;
    },
    onSuccess: (data, vars) => {
      try {
        if (data?.participante_token) localStorage.setItem(`qv_pt_${slug}`, data.participante_token);
        const saved = (vars?.nombre !== undefined ? vars.nombre : apodo || "").trim();
        if (saved) localStorage.setItem("qv_apodo", saved);
      } catch (e) { /* ignore */ }
      captureEvent("plan_response_submitted", { plan_id: slug, intencion: vars?.intencion, opcion_preferida: prefOpt || null });
      qc.setQueryData(["plan", slug], data.plan);
      setRespondFor(null);
      // Solo pedimos nombre si el servidor tuvo que inventarlo ("Invitado 3").
      const mineName = data?.plan?.mine?.apodo || "";
      const auto = /^Invitado\s+\d+$/i.test(mineName);
      if (auto && vars?.nombre === undefined) {
        setAskName(true);
        setNameDraft("");
        toast.success(t("planview.counted", "¡Contado! Ya apareces en el plan"));
      } else {
        setAskName(false);
        toast.success(t("planview.saved", "¡Respuesta guardada!"));
      }
    },
    onError: (e) => toast.error(e?.response?.data?.detail || t("planview.error", "No se pudo guardar")),
  });

  const inviteMut = useMutation({
    mutationFn: async (ids) => (await api.post(`/plans/${slug}/invite`, { user_ids: ids },
      { headers: ct ? { "x-participante-token": ct } : {} })).data,
    onSuccess: (data) => {
      if (data?.plan) qc.setQueryData(["plan", slug], data.plan);
      qc.invalidateQueries({ queryKey: ["plan-invitables", slug] });
      captureEvent("friend_invite_sent", { plan_id: slug, destination: "app", count: data?.invitados || 0 });
      setInviteOpen(false);
      setInvSel([]);
      toast.success(data?.invitados
        ? (data.invitados === 1
            ? t("planview.invited_ok_one", "Avisado 1 amigo")
            : t("planview.invited_ok", "Avisados {{n}} amigos", { n: data.invitados }))
        : t("planview.invited_none", "Ya estaban todos en el plan"));
    },
    onError: (e) => toast.error(e?.response?.data?.detail || t("planview.error", "No se pudo invitar")),
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
  // Always share the canonical /p/{slug} link: it is the one that renders the
  // rich WhatsApp preview and then redirects the human into the app.
  const shareUrl = typeof window !== "undefined" ? `${window.location.origin}/p/${slug}` : "";
  const shareWhatsApp = () => { captureEvent("plan_shared", { plan_id: slug, destination: "whatsapp" }); window.open(`https://wa.me/?text=${encodeURIComponent(`${shareText}: ${shareUrl}`)}`, "_blank", "noopener,noreferrer"); };
  const copyLink = async () => { captureEvent("plan_shared", { plan_id: slug, destination: "copy_link" }); try { await navigator.clipboard.writeText(shareUrl); toast.success(t("planview.copied", "Enlace copiado")); } catch (e) { /* ignore */ } };

  // Live Activity (Dynamic Island, solo app iOS): arranca con el plan abierto,
  // se actualiza al votar y se cierra cuando el plan se cierra o se cancela.
  useEffect(() => {
    if (!plan?.slug) return;
    if (plan.estado === "abierto") {
      startPlanActivity(plan);
      updatePlanActivity(plan);
    } else {
      updatePlanActivity(plan);
      endPlanActivity(plan.slug);
    }
  }, [plan]);

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
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-qv-secondary">{cityLabel}{fecha ? ` · ${fecha}` : ""}</p>
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
                <p className="text-xs font-bold uppercase tracking-wider text-white/50 mb-2">
                  {t("planview.who", "Quién responde")} ({counts.total || 0})
                  {counts.invitados ? <span className="text-white/35 normal-case font-semibold"> · {t("planview.pending_n", "{{n}} sin responder", { n: counts.invitados })}</span> : null}
                </p>
                <div className="flex flex-col gap-1.5">
                  {plan.participants.map((p, i) => (
                    <div key={i} className={`flex items-center gap-2.5 text-sm ${p.pendiente ? "opacity-55" : ""}`} data-testid={p.pendiente ? "planview-participant-pending" : "planview-participant"}>
                      <AvatarCircle name={p.apodo} picture={p.picture} size={26} ring={false} />
                      <span className="text-white/85 flex-1 truncate">
                        {p.apodo}
                        {p.pendiente ? <span className="text-white/40 text-xs"> · {t("planview.pending", "sin responder")}</span> : null}
                      </span>
                      <span>{p.emoji}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(plan.participants || []).length === 0 && !isClosed && (
              <p className="mt-4 text-sm text-white/45 leading-snug rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-3.5" data-testid="planview-empty">
                {t("planview.empty_hint", "Todavía no ha respondido nadie. Comparte el enlace: se responde en un toque, sin registrarse.")}
              </p>
            )}

            {/* Pull the voter into the rest of the app (this is the app, not a
                separate page): the parties of their city, one tap away. */}
            <button
              type="button"
              data-testid="planview-explore"
              onClick={() => navigate("/feed")}
              className="mt-4 w-full flex items-center gap-3 rounded-2xl border border-qv-secondary/30 bg-gradient-to-r from-qv-secondary/10 to-qv-primary/10 p-3.5 text-left active:scale-[0.99]"
            >
              <span className="w-9 h-9 rounded-xl bg-qv-secondary/15 flex items-center justify-center shrink-0">
                <PartyPopper className="w-4.5 h-4.5 text-qv-secondary" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-bold text-white">
                  {t("planview.explore_title", "Mira qué fiestas hay en {{city}}", { city: cityLabel || "tu ciudad" })}
                </span>
                <span className="block text-xs text-white/55">{t("planview.explore_sub", "Horarios, precios y quién va")}</span>
              </span>
              <Home className="w-4 h-4 text-white/30 shrink-0" />
            </button>

            {/* Your response status */}
            {plan.mine?.intencion && !isClosed ? (
              <div className="mt-4 rounded-2xl border border-white/12 bg-white/[0.04] p-3 flex items-center justify-between" data-testid="planview-mine">
                <p className="text-sm text-white/85">{t("planview.your_answer", "Tu respuesta")}: <b>{INTENTS.find((x) => x.key === plan.mine.intencion)?.emoji} {t(INTENTS.find((x) => x.key === plan.mine.intencion)?.labelKey, INTENTS.find((x) => x.key === plan.mine.intencion)?.label)}</b></p>
                <button onClick={() => setRespondFor(plan.mine.intencion)} className="text-xs font-bold text-qv-primary">{t("planview.change", "Cambiar")}</button>
              </div>
            ) : null}

            {/* El aviso de cierre va por notificación (no WhatsApp ni SMS). */}
            {plan.mine?.intencion && !isClosed ? (
              <p className="mt-1.5 text-white/40 text-[11px] leading-snug px-1">
                {user
                  ? t("planview.notify_push", "Te avisamos con una notificación en cuanto el plan se cierre.")
                  : t("planview.notify_signup", "¿Quieres que te avisemos al cerrarse el plan? Crea tu cuenta: tarda 10 segundos.")}
              </p>
            ) : null}

            {/* Te han invitado desde la app y aún no has contestado */}
            {plan.mine?.invitado && !isClosed ? (
              <div className="mt-4 rounded-2xl border border-qv-secondary/40 bg-qv-secondary/10 p-3.5" data-testid="planview-invited">
                <p className="text-sm text-white/90 font-semibold">{t("planview.invited_title", "Te han invitado a este plan")}</p>
                <p className="text-xs text-white/60 mt-0.5">{t("planview.invited_sub", "Dinos si te apuntas: tu grupo está esperando")}</p>
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

            {/* Invitar a amigos de la app (notificación directa, sin pasar por WhatsApp) */}
            {user && !isClosed ? (
              <button
                type="button"
                data-testid="planview-invite"
                onClick={() => { setInvSel([]); setInviteOpen(true); }}
                className="mt-2 w-full bg-white/[0.06] border border-qv-primary/35 text-white rounded-2xl py-2.5 font-bold text-sm flex items-center justify-center gap-1.5 active:scale-[0.99]"
              >
                <UserPlus className="w-4 h-4 text-qv-primary" /> {t("planview.invite_friends", "Invitar a mis amigos")}
              </button>
            ) : null}

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

        {/* Sticky response bar — un toque y ya cuentas (sin modal, sin registro) */}
        {plan && !isClosed && (!plan.mine?.intencion || respondFor) && !askName && (
          <div className="fixed bottom-[70px] left-0 right-0 z-20 px-4" data-testid="planview-respond-bar">
            <div className="mx-auto max-w-md bg-[#120d18]/95 backdrop-blur-md border border-white/12 rounded-2xl p-2 grid grid-cols-2 gap-2 shadow-2xl">
              {INTENTS.map((it) => (
                <button
                  key={it.key}
                  data-testid={`planview-intent-${it.key}`}
                  disabled={respondMut.isPending}
                  onClick={() => respondMut.mutate({ intencion: it.key })}
                  className={`h-11 rounded-xl font-bold text-sm flex items-center justify-center gap-1.5 active:scale-[0.98] disabled:opacity-60 ${btnClass(it.style, respondFor === it.key)}`}
                >
                  <span>{it.emoji}</span> {t(it.labelKey, it.label)}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Nombre DESPUÉS de votar y opcional: el voto ya está contado. */}
        {plan && askName && !isClosed && (
          <div className="fixed bottom-[70px] left-0 right-0 z-20 px-4" data-testid="planview-name-prompt">
            <div className="mx-auto max-w-md bg-[#120d18]/95 backdrop-blur-md border border-qv-primary/35 rounded-2xl p-3 shadow-2xl">
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm text-white/85 font-semibold">{t("planview.name_after", "Ya cuentas. ¿Cómo te llamamos?")}</p>
                <button onClick={() => setAskName(false)} data-testid="planview-name-skip" className="text-white/40 active:scale-90" aria-label="x"><X className="w-4 h-4" /></button>
              </div>
              <div className="flex items-center gap-2">
                <input
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  maxLength={40}
                  placeholder={t("planview.name_ph", "Alex")}
                  data-testid="planview-name-input"
                  onKeyDown={(e) => { if (e.key === "Enter" && nameDraft.trim()) { setApodo(nameDraft.trim()); respondMut.mutate({ intencion: plan.mine?.intencion || "dentro", nombre: nameDraft.trim() }); } }}
                  className="flex-1 min-w-0 bg-[#0a0712] border border-white/12 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-qv-primary/50"
                />
                <button
                  onClick={() => { if (!nameDraft.trim()) { setAskName(false); return; } setApodo(nameDraft.trim()); respondMut.mutate({ intencion: plan.mine?.intencion || "dentro", nombre: nameDraft.trim() }); }}
                  disabled={respondMut.isPending}
                  data-testid="planview-name-save"
                  className="shrink-0 h-10 px-4 rounded-xl bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white text-sm font-bold flex items-center justify-center disabled:opacity-60"
                >
                  {respondMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t("planview.name_done", "Listo")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Invitar amigos de la app a este plan */}
      <Drawer open={inviteOpen} onOpenChange={setInviteOpen}>
        <DrawerContent className="bg-[#120d18] border-t border-white/10 text-white focus:outline-none" data-testid="planview-invite-sheet">
          <div className="mx-auto w-full max-w-md px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-2">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display font-black text-lg">{t("planview.invite_title", "Invitar a mi grupo")}</h2>
              <button onClick={() => setInviteOpen(false)} className="text-white/40 active:scale-90" aria-label="x"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-white/45 text-xs mb-3">{t("planview.invite_sub", "Les llega un aviso y pueden votar en un toque")}</p>
            <FriendPicker slug={slug} selected={invSel} onChange={setInvSel} />
            <button
              onClick={() => inviteMut.mutate(invSel)}
              disabled={!invSel.length || inviteMut.isPending}
              data-testid="planview-invite-confirm"
              className="w-full mt-4 bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white rounded-2xl py-3.5 font-bold text-[15px] flex items-center justify-center gap-2 disabled:opacity-50 active:scale-[0.99]"
            >
              {inviteMut.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <UserPlus className="w-4 h-4" />}
              {invSel.length
                ? t("planview.invite_n", "Invitar a {{n}}", { n: invSel.length })
                : t("planview.invite_pick", "Elige a quién invitas")}
            </button>
          </div>
        </DrawerContent>
      </Drawer>
    </AppShell>
  );
}
