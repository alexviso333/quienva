import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ClipboardList, Plus, X, Check, Send, Link2, Loader2, PartyPopper, SlidersHorizontal, ChevronDown } from "lucide-react";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import FriendPicker from "@/components/FriendPicker";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import { captureEvent } from "@/analytics/posthog";

const MAX_OPTS = 3;

// In-app plan creation (bottom sheet). Replaces the old full-page /p/nuevo so the
// whole flow stays inside the app and matches its design. Two steps: form -> share.
// Kept intentionally minimal: by default only the "where" question is visible;
// title/quorum live behind an optional "Ajustes" disclosure so nothing feels crowded.
export default function CreatePlanSheet({ open, onOpenChange, presetEvent = null, city, source = "feed" }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState("form");
  const [titulo, setTitulo] = useState("");
  const [umbral, setUmbral] = useState("");
  const [showOpts, setShowOpts] = useState(false);
  const [rows, setRows] = useState([{ texto: "", hora: "", precio: "" }]);
  const [invitados, setInvitados] = useState([]); // user_ids de amigos de la app
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { slug, share_url, invitados }

  // Reset whenever the sheet opens.
  useEffect(() => {
    if (open) {
      setStep("form");
      setTitulo("");
      setUmbral("");
      setShowOpts(false);
      setRows(presetEvent ? [] : [{ texto: "", hora: "", precio: "" }]);
      setInvitados([]);
      setResult(null);
      setBusy(false);
    }
  }, [open, presetEvent]);

  const presetCount = presetEvent ? 1 : 0;
  const canAdd = rows.length + presetCount < MAX_OPTS;

  const addRow = () => { if (canAdd) setRows((r) => [...r, { texto: "", hora: "", precio: "" }]); };
  const rmRow = (i) => setRows((r) => r.filter((_, idx) => idx !== i));
  const setRow = (i, k, v) => setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [k]: v } : row)));

  // Track abandonment when the sheet is dismissed from the form (nothing created yet).
  const handleOpenChange = (next) => {
    if (!next && step === "form" && !result) {
      captureEvent("plan_create_abandoned", { step: "form", source: presetEvent ? "event" : source });
    }
    onOpenChange(next);
  };

  const submit = async () => {
    const opciones = [];
    if (presetEvent) {
      opciones.push({
        evento_id: presetEvent.id,
        venue_nombre: presetEvent.venue || presetEvent.name || "",
        hora: presetEvent.time || "",
        precio_desde: presetEvent.price || null,
      });
    }
    rows.forEach((r) => {
      const v = (r.texto || "").trim();
      if (v) opciones.push({ texto_libre: v, venue_nombre: v, hora: (r.hora || "").trim(), precio_desde: parseFloat(r.precio) || null });
    });
    if (!opciones.length) { toast.error(t("createplan.need_spot", "Añade al menos un sitio")); return; }
    setBusy(true);
    try {
      const body = {
        titulo: titulo.trim(),
        ciudad: city || presetEvent?.city || "Madrid",
        opciones,
        umbral_personas: parseInt(umbral, 10) || null,
        invitar_user_ids: invitados,
      };
      const { data } = await api.post("/plans", body);
      captureEvent("plan_created", { plan_id: data?.plan?.id, num_opciones: opciones.length, has_quorum: !!body.umbral_personas, source: presetEvent ? "event" : source, num_invitados: invitados.length });
      if (invitados.length) captureEvent("friend_invite_sent", { plan_id: data?.slug, destination: "app", count: invitados.length });
      try { if (data?.slug && data?.creador_token) localStorage.setItem(`qv_ct_${data.slug}`, data.creador_token); } catch (e) { /* ignore */ }
      setResult({ slug: data.slug, share_url: data.share_url, invitados: data.invitados || 0 });
      setStep("share");
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("createplan.error", "No se pudo crear el plan"));
    } finally {
      setBusy(false);
    }
  };

  const shareUrl = result?.share_url || "";
  const shareText = (() => {
    const nOpts = (presetEvent ? 1 : 0) + rows.filter((r) => (r.texto || "").trim()).length;
    if (nOpts > 1) return `Montando plan${titulo ? ` · ${titulo}` : ""}. He puesto ${nOpts} opciones, decidid cuál: ${shareUrl}`;
    if (umbral) return `${titulo || "Plan"} 🔥 Se cierra si somos ${umbral}. ¿Te apuntas?: ${shareUrl}`;
    return `👀 ${titulo || "¿Quién va?"} Dinos si te apuntas: ${shareUrl}`;
  })();

  const shareWhatsApp = () => {
    captureEvent("plan_shared", { plan_id: result?.slug, destination: "whatsapp" });
    window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, "_blank", "noopener,noreferrer");
  };
  const copyLink = async () => {
    captureEvent("plan_shared", { plan_id: result?.slug, destination: "copy_link" });
    try { await navigator.clipboard.writeText(shareUrl); toast.success(t("createplan.copied", "Enlace copiado")); } catch (e) { /* ignore */ }
  };

  const spotsLabel = presetEvent
    ? t("createplan.spots_alt", "¿Alguna alternativa? (opcional)")
    : t("createplan.spots", "¿Dónde quedáis?");

  return (
    <Drawer open={open} onOpenChange={handleOpenChange}>
      <DrawerContent className="bg-[#120d18] border-t border-white/10 text-white max-h-[92vh] focus:outline-none" data-testid="create-plan-sheet">
        <div className="mx-auto w-full max-w-md px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-1 overflow-y-auto">
          {step === "form" ? (
            <>
              <div className="flex items-center gap-2.5 mb-5">
                <div className="w-9 h-9 rounded-xl bg-qv-primary/15 border border-qv-primary/30 flex items-center justify-center shrink-0">
                  <ClipboardList className="w-[18px] h-[18px] text-qv-primary" />
                </div>
                <div>
                  <h2 className="font-display font-black text-lg leading-none">{t("createplan.title", "Monta tu plan")}</h2>
                  <p className="text-white/45 text-xs mt-1">{t("createplan.sub", "Comparte el link y tu grupo dice si se apunta")}</p>
                </div>
              </div>

              {presetEvent && (
                <div className="flex items-center gap-3 bg-white/[0.04] border border-qv-primary/30 rounded-2xl p-2.5 mb-4" data-testid="create-plan-preset">
                  {presetEvent.image_url ? (
                    <img src={presetEvent.image_url} alt="" className="w-12 h-12 rounded-xl object-cover shrink-0" />
                  ) : null}
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-sm truncate">{presetEvent.venue || presetEvent.name}</p>
                    <p className="text-white/45 text-xs truncate">{[presetEvent.time, presetEvent.price ? `desde ${presetEvent.price}€` : null].filter(Boolean).join(" · ")}</p>
                  </div>
                  <span className="text-[10px] text-qv-primary border border-qv-primary/40 rounded-full px-2 py-1 shrink-0">{t("createplan.included", "Incluido")}</span>
                </div>
              )}

              <p className="text-white/55 text-xs font-semibold mb-1.5">{spotsLabel}</p>
              <div className="flex flex-col gap-2">
                {rows.map((r, i) => (
                  <div key={i} className="flex items-center gap-2" data-testid={`create-plan-row-${i}`}>
                    <input
                      value={r.texto}
                      onChange={(e) => setRow(i, "texto", e.target.value)}
                      placeholder={t("createplan.spot_ph", "Sitio (p. ej. Fitz)")}
                      className="flex-1 min-w-0 bg-[#0a0712] border border-white/12 rounded-xl px-3 py-3 text-sm outline-none focus:border-qv-primary/50"
                    />
                    <input
                      value={r.hora}
                      onChange={(e) => setRow(i, "hora", e.target.value)}
                      placeholder={t("createplan.time", "Hora")}
                      className="w-16 bg-[#0a0712] border border-white/12 rounded-xl px-2 py-3 text-sm text-center outline-none focus:border-qv-primary/50"
                    />
                    {(rows.length > 1 || presetEvent) && (
                      <button onClick={() => rmRow(i)} className="text-white/35 active:scale-90 shrink-0" aria-label="x">
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {canAdd && (
                <button onClick={addRow} data-testid="create-plan-add" className="mt-2 w-full border border-dashed border-white/15 text-qv-primary/90 rounded-xl py-2.5 text-sm font-semibold flex items-center justify-center gap-1.5 active:scale-[0.99]">
                  <Plus className="w-4 h-4" /> {t("createplan.add_spot", "Añadir otra opción")}
                </button>
              )}

              {/* Invitar a amigos de la app: se les avisa con una notificación y
                  entran como "pendientes" hasta que contestan. El enlace de
                  WhatsApp sigue estando para los que no tienen la app. */}
              {user ? (
                <div className="mt-4" data-testid="create-plan-friends">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-white/55 text-xs font-semibold">{t("createplan.who_label", "¿A quién avisas?")}</p>
                    {invitados.length ? (
                      <span className="text-[11px] font-bold text-qv-primary">{invitados.length === 1
                        ? t("createplan.who_count_one", "1 seleccionado")
                        : t("createplan.who_count", "{{n}} seleccionados", { n: invitados.length })}</span>
                    ) : (
                      <span className="text-[11px] text-white/35">{t("createplan.who_hint", "opcional")}</span>
                    )}
                  </div>
                  <FriendPicker selected={invitados} onChange={setInvitados} />
                </div>
              ) : null}

              {/* Optional settings, hidden by default so the default view stays clean */}
              {!showOpts ? (
                <button
                  onClick={() => setShowOpts(true)}
                  data-testid="create-plan-more"
                  className="mt-4 w-full flex items-center justify-center gap-1.5 text-white/45 text-xs font-medium py-1.5 active:scale-[0.99]"
                >
                  <SlidersHorizontal className="w-3.5 h-3.5" /> {t("createplan.more_opts", "Título y aforo (opcional)")}
                  <ChevronDown className="w-3.5 h-3.5" />
                </button>
              ) : (
                <div className="mt-4 grid grid-cols-2 gap-2" data-testid="create-plan-opts">
                  <div>
                    <p className="text-white/45 text-[11px] mb-1">{t("createplan.name_opt", "Título")}</p>
                    <input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={60}
                      placeholder={t("createplan.name_ph", "Jueves en Chueca")}
                      className="w-full bg-[#0a0712] border border-white/12 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-qv-primary/50" />
                  </div>
                  <div>
                    <p className="text-white/45 text-[11px] mb-1">{t("createplan.quorum_opt", "Se cierra si somos")}</p>
                    <input value={umbral} onChange={(e) => setUmbral(e.target.value.replace(/\D/g, ""))} inputMode="numeric"
                      placeholder={t("createplan.quorum_ph", "p. ej. 6")}
                      className="w-full bg-[#0a0712] border border-white/12 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-qv-primary/50" />
                  </div>
                </div>
              )}

              <button onClick={submit} disabled={busy} data-testid="create-plan-submit"
                className="w-full mt-5 bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white rounded-2xl py-3.5 font-bold text-[15px] flex items-center justify-center gap-2 disabled:opacity-60 active:scale-[0.99] shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]">
                {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-4 h-4" />}
                {invitados.length
                  ? t("createplan.create_invite", "Crear y avisar a {{n}}", { n: invitados.length })
                  : t("createplan.create", "Crear y compartir")}
              </button>
              <button onClick={() => handleOpenChange(false)} className="w-full mt-2 text-white/40 text-sm py-1.5">{t("createplan.cancel", "Cancelar")}</button>
            </>
          ) : (
            <div className="text-center pt-3" data-testid="create-plan-share">
              <div className="w-14 h-14 rounded-full bg-qv-primary/15 border border-qv-primary/30 flex items-center justify-center mx-auto mb-3">
                <PartyPopper className="w-7 h-7 text-qv-primary" />
              </div>
              <h2 className="font-display font-black text-xl">{t("createplan.done_title", "¡Plan creado!")}</h2>
              {result?.invitados ? (
                <p className="text-sm mt-1 mb-5 text-white/55" data-testid="create-plan-invited">
                  <b className="text-qv-primary">{result.invitados === 1
                    ? t("createplan.done_invited_one", "Avisado 1 amigo")
                    : t("createplan.done_invited", "Avisados {{n}} amigos", { n: result.invitados })}</b>
                  {" · "}
                  {t("createplan.done_invited_sub", "comparte el enlace con los que no tienen la app")}
                </p>
              ) : (
                <p className="text-white/55 text-sm mt-1 mb-5">{t("createplan.done_sub", "Compártelo con tu grupo para que digan si se apuntan")}</p>
              )}

              <button onClick={shareWhatsApp} data-testid="create-plan-wa"
                className="w-full bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white rounded-2xl py-3.5 font-bold text-[15px] flex items-center justify-center gap-2 active:scale-[0.99]">
                <Send className="w-4 h-4" /> {t("createplan.share_wa", "Compartir por WhatsApp")}
              </button>
              <div className="grid grid-cols-2 gap-2 mt-2">
                <button onClick={copyLink} className="bg-white/[0.06] border border-white/12 text-white/85 rounded-2xl py-3 font-semibold text-sm flex items-center justify-center gap-1.5 active:scale-[0.99]">
                  <Link2 className="w-4 h-4" /> {t("createplan.copy", "Copiar enlace")}
                </button>
                <button
                  type="button"
                  data-testid="create-plan-view"
                  onClick={() => { onOpenChange(false); navigate(`/plan/${result?.slug}`); }}
                  className="bg-white/[0.06] border border-white/12 text-white/85 rounded-2xl py-3 font-semibold text-sm flex items-center justify-center gap-1.5 active:scale-[0.99]">
                  <Check className="w-4 h-4" /> {t("createplan.view", "Ver plan")}
                </button>
              </div>
              <button onClick={() => onOpenChange(false)} className="w-full mt-3 text-white/40 text-sm py-1.5">{t("createplan.close", "Hecho")}</button>
            </div>
          )}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
