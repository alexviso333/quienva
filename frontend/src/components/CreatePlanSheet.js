import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ClipboardList, Plus, X, Check, Send, Link2, Loader2, PartyPopper, SlidersHorizontal, ChevronDown, Search, Building2, Flame, PencilLine, MapPin } from "lucide-react";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import FriendPicker from "@/components/FriendPicker";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import { captureEvent } from "@/analytics/posthog";
import { startPlanActivity } from "@/lib/liveActivity";

const MAX_OPTS = 3;
const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const DAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const dayLabel = (iso) => {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return `${DAYS[d.getDay()]} ${d.getDate()}`;
};

let uid = 0;
const nextKey = () => `o${++uid}`;

/* -------------------------------------------------------------------------- */
/* Fila seleccionable del buscador (evento o discoteca)                        */
/* -------------------------------------------------------------------------- */
function PickRow({ image, title, sub, onPick, testid, disabled }) {
  return (
    <button
      type="button"
      data-testid={testid}
      onClick={onPick}
      disabled={disabled}
      className="w-full flex items-center gap-2.5 rounded-xl px-2 py-2 text-left active:scale-[0.99] disabled:opacity-40 hover:bg-white/[0.05] transition-colors"
    >
      {image ? (
        <img src={image} alt="" className="w-10 h-10 rounded-lg object-cover shrink-0" />
      ) : (
        <span className="w-10 h-10 rounded-lg bg-white/[0.07] flex items-center justify-center shrink-0">
          <Building2 className="w-4 h-4 text-white/40" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-[13px] text-white truncate">{title}</span>
        {sub ? <span className="block text-[11px] text-white/45 truncate">{sub}</span> : null}
      </span>
      <Plus className="w-4 h-4 text-qv-primary shrink-0" />
    </button>
  );
}

// In-app plan creation (bottom sheet). Dos pasos: formulario -> compartir.
// El formulario arranca con un selector de opciones (eventos reales de la
// ciudad, directorio de discotecas o texto libre) para que montar la votación
// sea un par de toques en vez de escribir nombres a mano.
export default function CreatePlanSheet({ open, onOpenChange, presetEvent = null, city, source = "feed" }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState("form");
  const [titulo, setTitulo] = useState("");
  const [umbral, setUmbral] = useState("");
  const [showOpts, setShowOpts] = useState(false);
  const [opts, setOpts] = useState([]);          // opciones elegidas (máx 3)
  const [tab, setTab] = useState("eventos");     // eventos | locales | manual
  const [pickQ, setPickQ] = useState("");
  const [manual, setManual] = useState({ texto: "", hora: "" });
  const [invitados, setInvitados] = useState([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const effCity = city || presetEvent?.city || user?.city || "Palma de Mallorca";

  const presetOpt = presetEvent
    ? {
        key: "preset",
        kind: "event",
        evento_id: presetEvent.id,
        nombre: presetEvent.venue || presetEvent.name || "",
        hora: presetEvent.time || "",
        precio: presetEvent.price || null,
        image_url: presetEvent.image_url || "",
      }
    : null;

  useEffect(() => {
    if (open) {
      setStep("form");
      setTitulo("");
      setUmbral("");
      setShowOpts(false);
      setOpts(presetOpt ? [presetOpt] : []);
      setTab("eventos");
      setPickQ("");
      setManual({ texto: "", hora: "" });
      setInvitados([]);
      setResult(null);
      setBusy(false);
    }
     
  }, [open, presetEvent]);

  // Catálogos para el selector (solo se piden cuando la hoja está abierta).
  const { data: events = [], isLoading: loadingEvents } = useQuery({
    queryKey: ["events", effCity, "all"],
    queryFn: async () => (await api.get("/events", { params: { date_filter: "all", city: effCity } })).data,
    enabled: open,
    staleTime: 60_000,
  });
  const { data: venues = [], isLoading: loadingVenues } = useQuery({
    queryKey: ["venues", effCity],
    queryFn: async () => (await api.get("/venues", { params: { city: effCity } })).data,
    enabled: open && tab === "locales",
    staleTime: 300_000,
  });

  const canAdd = opts.length < MAX_OPTS;
  const takenEvents = new Set(opts.filter((o) => o.evento_id).map((o) => o.evento_id));
  const takenNames = new Set(opts.map((o) => norm(o.nombre)));

  const filteredEvents = useMemo(() => {
    const tk = norm(pickQ).split(/\s+/).filter(Boolean);
    return (events || [])
      .filter((e) => {
        if (takenEvents.has(e.id)) return false;
        if (!tk.length) return true;
        const hay = norm(`${e.name} ${e.venue} ${e.genre}`);
        return tk.every((x) => hay.includes(x));
      })
      .slice(0, 40);
     
  }, [events, pickQ, opts]);

  const filteredVenues = useMemo(() => {
    const tk = norm(pickQ).split(/\s+/).filter(Boolean);
    return (venues || [])
      .filter((v) => {
        if (takenNames.has(norm(v.name))) return false;
        if (!tk.length) return true;
        const hay = norm(`${v.name} ${v.zone} ${v.type}`);
        return tk.every((x) => hay.includes(x));
      })
      .slice(0, 40);
     
  }, [venues, pickQ, opts]);

  const addOpt = (o) => {
    if (!canAdd) { toast.error(t("createplan.max_opts", "Máximo 3 opciones para votar")); return; }
    setOpts((prev) => [...prev, { ...o, key: nextKey() }]);
    setPickQ("");
  };
  const addEvent = (e) => addOpt({
    kind: "event",
    evento_id: e.id,
    nombre: e.name || e.venue || "",
    sub: [e.venue, dayLabel(e.date), e.time].filter(Boolean).join(" · "),
    hora: e.time || "",
    precio: e.current_price || null,
    image_url: e.image_url || "",
  });
  const addVenue = (v) => addOpt({
    kind: "venue",
    nombre: v.name || "",
    sub: [v.zone, v.type].filter(Boolean).join(" · "),
    hora: "",
    precio: null,
    image_url: v.image_url || v.photo || "",
  });
  const addManual = () => {
    const v = manual.texto.trim();
    if (!v) return;
    addOpt({ kind: "free", nombre: v, hora: manual.hora.trim(), precio: null, image_url: "" });
    setManual({ texto: "", hora: "" });
  };
  const rmOpt = (key) => setOpts((prev) => prev.filter((o) => o.key !== key));

  const handleOpenChange = (next) => {
    if (!next && step === "form" && !result) {
      captureEvent("plan_create_abandoned", { step: "form", source: presetEvent ? "event" : source });
    }
    onOpenChange(next);
  };

  const submit = async () => {
    if (!opts.length) { toast.error(t("createplan.need_spot", "Añade al menos un sitio")); return; }
    const opciones = opts.map((o) => (
      o.evento_id
        ? { evento_id: o.evento_id, venue_nombre: o.nombre, hora: o.hora || "", precio_desde: o.precio || null }
        : { texto_libre: o.nombre, venue_nombre: o.nombre, hora: o.hora || "", precio_desde: o.precio || null }
    ));
    setBusy(true);
    try {
      const body = {
        titulo: titulo.trim(),
        ciudad: effCity,
        opciones,
        umbral_personas: parseInt(umbral, 10) || null,
        invitar_user_ids: invitados,
      };
      const { data } = await api.post("/plans", body);
      captureEvent("plan_created", {
        plan_id: data?.plan?.id,
        num_opciones: opciones.length,
        has_quorum: !!body.umbral_personas,
        source: presetEvent ? "event" : source,
        num_invitados: invitados.length,
        kinds: opts.map((o) => o.kind).join(","),
      });
      if (invitados.length) captureEvent("friend_invite_sent", { plan_id: data?.slug, destination: "app", count: invitados.length });
      try { if (data?.slug && data?.creador_token) localStorage.setItem(`qv_ct_${data.slug}`, data.creador_token); } catch (e) { /* ignore */ }
      setResult({ slug: data.slug, share_url: data.share_url, invitados: data.invitados || 0 });
      // Isla dinámica / pantalla de bloqueo desde el segundo 0 (solo iOS nativo).
      if (data?.plan) startPlanActivity(data.plan);
      setStep("share");
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("createplan.error", "No se pudo crear el plan"));
    } finally {
      setBusy(false);
    }
  };

  const shareUrl = result?.share_url || "";
  const shareText = (() => {
    if (opts.length > 1) return `Montando plan${titulo ? ` · ${titulo}` : ""}. He puesto ${opts.length} opciones, votad cuál: ${shareUrl}`;
    if (umbral) return `${titulo || opts[0]?.nombre || "Plan"} 🔥 Se cierra si somos ${umbral}. ¿Te apuntas?: ${shareUrl}`;
    return `👀 ${titulo || opts[0]?.nombre || "¿Quién va?"} Dinos si te apuntas: ${shareUrl}`;
  })();

  const shareWhatsApp = () => {
    captureEvent("plan_shared", { plan_id: result?.slug, destination: "whatsapp" });
    window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, "_blank", "noopener,noreferrer");
  };
  const copyLink = async () => {
    captureEvent("plan_shared", { plan_id: result?.slug, destination: "copy_link" });
    try { await navigator.clipboard.writeText(shareUrl); toast.success(t("createplan.copied", "Enlace copiado")); } catch (e) { /* ignore */ }
  };

  const tabs = [
    { id: "eventos", label: t("createplan.tab_events", "Fiestas"), icon: Flame },
    { id: "locales", label: t("createplan.tab_venues", "Discotecas"), icon: Building2 },
    { id: "manual", label: t("createplan.tab_manual", "A mano"), icon: PencilLine },
  ];

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
                  <p className="text-white/45 text-xs mt-1">{t("createplan.sub2", "Elige hasta 3 sitios y tu grupo vota")}</p>
                </div>
              </div>

              {/* --- Opciones elegidas --- */}
              <div className="flex items-center justify-between mb-2">
                <p className="text-white/55 text-xs font-semibold">
                  {opts.length > 1 ? t("createplan.voting_on", "Se vota entre:") : t("createplan.spots", "¿Dónde quedáis?")}
                </p>
                <span className="text-[11px] font-bold text-white/35">{opts.length}/{MAX_OPTS}</span>
              </div>

              {opts.length > 0 ? (
                <div className="flex flex-col gap-2 mb-3" data-testid="create-plan-chosen">
                  {opts.map((o, i) => (
                    <div key={o.key} className="flex items-center gap-2.5 bg-white/[0.045] border border-qv-primary/25 rounded-2xl p-2" data-testid={`create-plan-opt-${i}`}>
                      {o.image_url ? (
                        <img src={o.image_url} alt="" className="w-11 h-11 rounded-xl object-cover shrink-0" />
                      ) : (
                        <span className="w-11 h-11 rounded-xl bg-qv-primary/12 flex items-center justify-center shrink-0">
                          <MapPin className="w-4 h-4 text-qv-primary" />
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-sm truncate">{o.nombre}</p>
                        <p className="text-white/45 text-[11px] truncate">
                          {o.sub || [o.hora, o.precio ? `desde ${o.precio}€` : null].filter(Boolean).join(" · ") || t("createplan.free_opt", "Escrito por ti")}
                        </p>
                      </div>
                      <button onClick={() => rmOpt(o.key)} data-testid={`create-plan-opt-rm-${i}`} className="text-white/35 active:scale-90 shrink-0 p-1" aria-label="quitar">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-white/35 text-xs mb-3" data-testid="create-plan-empty-hint">
                  {t("createplan.pick_hint", "Elige una fiesta, una discoteca o escríbelo tú.")}
                </p>
              )}

              {/* --- Selector: fiestas / discotecas / a mano --- */}
              {canAdd && (
                <div className="rounded-2xl border border-white/10 bg-[#0d0916] p-2.5" data-testid="create-plan-picker">
                  <div className="grid grid-cols-3 gap-1 bg-white/[0.04] rounded-xl p-1">
                    {tabs.map((tb) => (
                      <button
                        key={tb.id}
                        type="button"
                        data-testid={`create-plan-tab-${tb.id}`}
                        onClick={() => { setTab(tb.id); setPickQ(""); }}
                        className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-[12px] font-bold transition-colors ${
                          tab === tb.id ? "bg-qv-primary text-white shadow-[0_6px_16px_-8px_rgba(255,0,85,0.9)]" : "text-white/50"
                        }`}
                      >
                        <tb.icon className="w-3.5 h-3.5" /> {tb.label}
                      </button>
                    ))}
                  </div>

                  {tab === "manual" ? (
                    <div className="flex items-center gap-2 mt-2.5">
                      <input
                        value={manual.texto}
                        onChange={(e) => setManual((m) => ({ ...m, texto: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addManual(); } }}
                        placeholder={t("createplan.spot_ph", "Sitio (p. ej. casa de Marta)")}
                        data-testid="create-plan-manual-input"
                        className="flex-1 min-w-0 bg-[#0a0712] border border-white/12 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-qv-primary/50"
                      />
                      <input
                        value={manual.hora}
                        onChange={(e) => setManual((m) => ({ ...m, hora: e.target.value }))}
                        placeholder={t("createplan.time", "Hora")}
                        data-testid="create-plan-manual-time"
                        className="w-16 bg-[#0a0712] border border-white/12 rounded-xl px-2 py-2.5 text-sm text-center outline-none focus:border-qv-primary/50"
                      />
                      <button
                        type="button"
                        onClick={addManual}
                        data-testid="create-plan-manual-add"
                        className="shrink-0 w-10 h-10 rounded-xl bg-qv-primary/20 border border-qv-primary/40 text-qv-primary flex items-center justify-center active:scale-95"
                        aria-label="añadir"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="relative mt-2.5">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40 pointer-events-none" />
                        <input
                          value={pickQ}
                          onChange={(e) => setPickQ(e.target.value)}
                          data-testid="create-plan-pick-search"
                          placeholder={tab === "eventos"
                            ? t("createplan.search_events", "Busca una fiesta de {{city}}…", { city: effCity.split(",")[0] })
                            : t("createplan.search_venues", "Busca una discoteca…")}
                          className="w-full bg-[#0a0712] border border-white/12 rounded-xl pl-9 pr-3 py-2.5 text-sm outline-none focus:border-qv-primary/50"
                        />
                      </div>
                      <div className="mt-1.5 max-h-[216px] overflow-y-auto flex flex-col gap-0.5" data-testid="create-plan-pick-list">
                        {(tab === "eventos" ? loadingEvents : loadingVenues) ? (
                          <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-white/40" /></div>
                        ) : tab === "eventos" ? (
                          filteredEvents.length ? filteredEvents.map((e) => (
                            <PickRow
                              key={e.id}
                              testid={`create-plan-pick-event-${e.id}`}
                              image={e.image_url}
                              title={e.name || e.venue}
                              sub={[e.venue, dayLabel(e.date), e.time].filter(Boolean).join(" · ")}
                              onPick={() => addEvent(e)}
                            />
                          )) : (
                            <p className="text-white/35 text-xs text-center py-5">{t("createplan.no_events", "No hay fiestas que encajen. Prueba en «Discotecas» o escríbelo a mano.")}</p>
                          )
                        ) : (
                          filteredVenues.length ? filteredVenues.map((v) => (
                            <PickRow
                              key={v.id}
                              testid={`create-plan-pick-venue-${v.id}`}
                              image={v.image_url || v.photo}
                              title={v.name}
                              sub={[v.zone, v.upcoming_events ? `${v.upcoming_events} fiestas` : null].filter(Boolean).join(" · ")}
                              onPick={() => addVenue(v)}
                            />
                          )) : (
                            <p className="text-white/35 text-xs text-center py-5">{t("createplan.no_venues", "Ninguna discoteca coincide.")}</p>
                          )
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Invitar a amigos de la app */}
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

              {/* Ajustes opcionales */}
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

              <button onClick={submit} disabled={busy || !opts.length} data-testid="create-plan-submit"
                className="w-full mt-5 bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white rounded-2xl py-3.5 font-bold text-[15px] flex items-center justify-center gap-2 disabled:opacity-50 active:scale-[0.99] shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]">
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
