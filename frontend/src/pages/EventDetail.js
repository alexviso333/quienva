import { useState, useEffect } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb, API } from "@/lib/api";
import { setReturnEvent } from "@/lib/returnEvent";
import { formatPartyDate } from "@/lib/format";
import { AvatarCircle } from "@/components/AvatarCircle";
import { BlurredGoingTeaser } from "@/components/BlurredGoingTeaser";
import { EventAlbum } from "@/components/EventAlbum";
import { EventMoment } from "@/components/EventMoment";
import FourvenuesEmbed from "@/components/FourvenuesEmbed";
import { NightRecapCard } from "@/components/NightRecapCard";
import { EventOpenPlans } from "@/components/EventOpenPlans";
import { VenueNights } from "@/components/VenueNights";
import { VoyCelebration } from "@/components/VoyCelebration";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";
import { useCreatePlan } from "@/context/CreatePlan";
import {
  ArrowLeft, MapPin, Clock, Ticket, ExternalLink, Send, Check, Star, Navigation, CheckCircle2, Loader2, Bell, Instagram, Pencil, X, RotateCcw, Users, Eye, ClipboardList,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { captureEvent } from "@/analytics/posthog";

const todayStr = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
};

// Optimistic interest change: flip my_status + adjust the split counts instantly
// so the card reacts with zero perceived delay (no toast, no spinner).
const applyIntent = (e, status) => {
  if (!e) return e;
  const prev = e.my_status;
  if (prev === status) return e;
  let gc = e.going_count ?? 0;
  let ic = e.interested_count ?? 0;
  if (prev === "voy") gc = Math.max(0, gc - 1);
  if (prev === "me_interesa") ic = Math.max(0, ic - 1);
  if (status === "voy") gc += 1;
  if (status === "me_interesa") ic += 1;
  return { ...e, my_status: status, going_count: gc, interested_count: ic };
};

const FIELD_LABELS = {
  name: "Nombre", venue: "Discoteca", address: "Dirección", date: "Fecha",
  time: "Hora", image_url: "Foto", genre: "Género", city: "Ciudad",
  sale_state: "Estado", price_tiers: "Precio", link_override: "Enlace manual",
};
const fmtEditVal = (v) => {
  if (v === "" || v === null || v === undefined) return "(vacío)";
  if (Array.isArray(v)) return v.map((t) => `${t.name || ""} ${t.price ?? ""}€`).join(", ") || "(vacío)";
  const s = String(v);
  return s.length > 44 ? s.slice(0, 44) + "…" : s;
};

function FriendRow({ title, color, friends }) {
  if (!friends || friends.length === 0) return null;
  return (
    <div>
      <p className="text-xs uppercase tracking-widest font-bold mb-2" style={{ color }}>
        {title} ({friends.length})
      </p>
      <div className="flex flex-col gap-2">
        {friends.map((f) => (
          <div key={f.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-2.5">
            <AvatarCircle name={f.name} picture={f.picture} size={38} ring={false} />
            <span className="font-semibold text-sm">{f.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function EventDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { user } = useAuth();
  const { requireAuth } = useGuestGate();
  const { open: openCreatePlan } = useCreatePlan();
  const navigate = useNavigate();
  const [storyBusy, setStoryBusy] = useState(false);
  const isAdmin = user?.role === "admin";
  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState(null);
  const [peopleSheet, setPeopleSheet] = useState(null); // null | "voy" | "me_interesa"
  const [celebrateKey, setCelebrateKey] = useState(0);
  const location = useLocation();
  // Robust "back": if the user landed here directly (shared link, notification,
  // refresh) there is no in-app history to pop, so navigate(-1) would do nothing
  // or leave the app. In that case fall back to the feed.
  const goBack = () => {
    if (location.key && location.key !== "default") {
      navigate(-1);
    } else {
      navigate("/feed");
    }
  };
  const qc = useQueryClient();

  const { data: event, isLoading, isError } = useQuery({
    queryKey: ["event", id],
    queryFn: async () => (await api.get(`/events/${id}`)).data,
    // Instant open: reuse the event already cached from the feed/carousel lists
    // as placeholder so the panel paints immediately instead of showing a
    // full-screen spinner while the detailed payload loads in the background.
    placeholderData: () => {
      try {
        for (const [, data] of qc.getQueriesData({})) {
          if (!data) continue;
          const arr = Array.isArray(data)
            ? data
            : Array.isArray(data?.events)
              ? data.events
              : Array.isArray(data?.items)
                ? data.items
                : null;
          if (arr) {
            const hit = arr.find((e) => e && e.id === id);
            if (hit) return hit;
          }
        }
      } catch {
        /* ignore */
      }
      return undefined;
    },
    staleTime: 30_000,
    // A genuine 404 (party removed/rescheduled) must NOT retry — show the
    // friendly "no longer available" screen immediately instead of hanging.
    retry: (count, err) => (err?.response?.status === 404 ? false : count < 2),
  });

  // Sprint 3: a guest who lands on this public event (e.g. from a WhatsApp
  // share) should return right here after signing up, with avatars unlocked.
  useEffect(() => {
    if (!user && id) setReturnEvent(id);
  }, [user, id]);

  // Analytics: named event-page view (in addition to the generic $pageview).
  useEffect(() => {
    if (id) captureEvent("event_page_viewed", { evento_id: id });
  }, [id]);

  // Who's going / interested — loaded only when the sheet is open (logged-in).
  const { data: peopleData, isLoading: peopleLoading } = useQuery({
    queryKey: ["event-people", id, peopleSheet],
    queryFn: async () => (await api.get(`/events/${id}/people`, { params: { status: peopleSheet } })).data,
    enabled: !!peopleSheet && !!user,
    staleTime: 15_000,
  });

  const setStatus = useMutation({
    mutationFn: async (status) => (await api.post(`/events/${id}/interest`, { status })).data,
    onMutate: async (status) => {
      await qc.cancelQueries({ queryKey: ["event", id] });
      const prev = qc.getQueryData(["event", id]);
      qc.setQueryData(["event", id], (e) => applyIntent(e, status));
      const patchArr = (arr) =>
        Array.isArray(arr) ? arr.map((e) => (e.id === id ? applyIntent(e, status) : e)) : arr;
      qc.getQueriesData({ queryKey: ["events"] }).forEach(([key, data]) => {
        qc.setQueryData(key, patchArr(data));
      });
      return { prev };
    },
    // No success toast: the optimistic update is instant, a toast would only
    // draw attention to the network round-trip.
    onError: (_e, _s, ctx) => {
      if (ctx?.prev) qc.setQueryData(["event", id], ctx.prev);
      toast.error(t("event.toast_error"));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["event", id] });
      qc.invalidateQueries({ queryKey: ["events"] });
    },
  });

  const setTicket = useMutation({
    mutationFn: async (have) => (await api.post(`/events/${id}/ticket`, { have })).data,
    onMutate: async (have) => {
      await qc.cancelQueries({ queryKey: ["event", id] });
      const prev = qc.getQueryData(["event", id]);
      qc.setQueryData(["event", id], (e) => (e ? { ...e, my_has_ticket: have } : e));
      return { prev };
    },
    onSuccess: (_d, have) => {
      if (have) toast.success("¡Guardado! 🎟️ Tus amigos verán que vas con entrada");
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["event", id], ctx.prev);
      toast.error(t("event.toast_ticket_error"));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["event", id] }),
  });

  const setFollow = useMutation({
    mutationFn: async (follow) =>
      follow
        ? (await api.post(`/events/${id}/follow`)).data
        : (await api.delete(`/events/${id}/follow`)).data,
    onMutate: async (follow) => {
      await qc.cancelQueries({ queryKey: ["event", id] });
      const prev = qc.getQueryData(["event", id]);
      qc.setQueryData(["event", id], (e) => (e ? { ...e, is_following: follow } : e));
      return { prev };
    },
    onSuccess: (_d, follow) =>
      toast.success(follow ? "Te avisaremos de cambios 🔔" : "Avisos desactivados"),
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["event", id], ctx.prev);
      toast.error(t("event.toast_follow_error"));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["event", id] }),
  });

  // ---- Admin-only: edit event (pencil) ----
  const openEdit = () => {
    setForm({
      name: event.name || "",
      venue: event.venue || "",
      address: event.address || "",
      date: event.date || "",
      time: event.time || "",
      genre: event.genre || "",
      image_url: event.image_url || "",
      city: event.city || "",
      // The manual buy-link override (sticky). Prefill with the current override if
      // set, otherwise leave blank so the automatic link keeps mandando (option B).
      link_override: event.link_override || "",
    });
    setEditOpen(true);
  };

  const saveEdit = useMutation({
    mutationFn: async (payload) =>
      (await api.put(`/admin/events/${id}/admin-edit`, payload)).data,
    onSuccess: () => {
      toast.success("Evento actualizado");
      setEditOpen(false);
      qc.invalidateQueries({ queryKey: ["event", id] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["event-edit-history", id] });
    },
    onError: () => toast.error("No se pudo guardar"),
  });

  // Edit history (who/when changed what) + undo — loaded when the modal is open.
  const { data: editHistory } = useQuery({
    queryKey: ["event-edit-history", id],
    queryFn: async () => (await api.get(`/admin/events/${id}/edit-history`)).data,
    enabled: isAdmin && editOpen,
  });
  const undoEdit = useMutation({
    mutationFn: async (editId) => (await api.post(`/admin/events/${id}/edit-history/${editId}/undo`)).data,
    onSuccess: () => {
      toast.success("Cambio deshecho");
      qc.invalidateQueries({ queryKey: ["event", id] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["event-edit-history", id] });
    },
    onError: () => toast.error("No se pudo deshacer"),
  });

  const submitEdit = (e) => {
    e?.preventDefault?.();
    if (!form) return;
    const payload = {
      name: form.name,
      venue: form.venue,
      address: form.address,
      date: form.date,
      time: form.time,
      genre: form.genre,
      image_url: form.image_url,
      city: form.city,
    };
    // Sticky buy-link override: only send it when the admin actually typed one.
    const lo = (form.link_override || "").trim();
    const currentOverride = (event.link_override || "").trim();
    if (lo) {
      payload.link_override = lo;
    } else if (currentOverride) {
      // Field was cleared → remove the override, back to automatic.
      payload.clear_link_override = true;
    }
    saveEdit.mutate(payload);
  };

  const resetLinkOverride = () => {
    setForm((f) => ({ ...f, link_override: "" }));
    saveEdit.mutate({ clear_link_override: true });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen qv-app-bg flex items-center justify-center">
        <Loader2 className="w-7 h-7 text-qv-primary animate-spin" />
      </div>
    );
  }

  // The party is no longer available (removed, cancelled or rescheduled). NEVER
  // show a raw 404 / stuck spinner: give the user a friendly screen + a way back
  // to the feed so a shared link is never a dead end.
  if (isError || !event) {
    return (
      <div className="min-h-screen qv-app-bg flex flex-col items-center justify-center text-center px-8">
        <div className="text-5xl mb-4">🎉</div>
        <h1 className="text-white text-xl font-bold mb-2">Esta fiesta ya no está disponible</h1>
        <p className="text-white/60 text-sm mb-8 max-w-xs">
          Puede que se haya cancelado o cambiado de fecha. ¡Descubre otros planes cerca de ti!
        </p>
        <button
          data-testid="event-notfound-feed-btn"
          onClick={() => navigate("/feed")}
          className="h-12 px-8 rounded-2xl bg-qv-primary text-white font-bold text-base active:scale-95 transition-transform"
        >
          Ver otras fiestas
        </button>
      </div>
    );
  }

  const isPast = event.date < todayStr();
  const isVoy = event.my_status === "voy";
  const isInteresa = event.my_status === "me_interesa";
  const isEstuve = event.my_status === "estuve";
  const toggle = (s) => {
    if (!requireAuth("apuntarte a este plan")) return;
    const next = event.my_status === s ? "none" : s;
    if (s === "voy" && next === "voy") setCelebrateKey((k) => k + 1);
    setStatus.mutate(next);
  };

  const mapQuery = encodeURIComponent(`${event.address || event.venue}, ${event.city || "Palma de Mallorca"}`);
  const shareWhatsApp = () => {
    const link = `${API}/share/event/${event.id}`;
    const text = `${event.name} — ¿vienes? 👀\n${link}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
  };

  // One-tap Instagram Story: fetch the ready-made 1080x1920 image from the
  // backend and open the native share sheet (Instagram/Stories) with the file;
  // if the device can't share files, download it so it can be posted manually.
  const shareStory = async (style = "neon") => {
    if (storyBusy) return;
    setStoryBusy(true);
    try {
      const res = await fetch(`${API}/story-image/${event.id}?style=${style}`);
      if (!res.ok) throw new Error("img");
      const blob = await res.blob();
      const file = new File([blob], `quienva-${event.id}.jpg`, { type: "image/jpeg" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: event.name, text: `${event.name} — ¿vienes? 👀` });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `quienva-${event.id}.jpg`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }
    } catch (_e) {
      /* user cancelled or share unsupported — ignore */
    } finally {
      setStoryBusy(false);
    }
  };

  const hasInterest = !!event.my_status && event.my_status !== "none";

  const onTicketClick = () => {
    // Fire-and-forget tracking for the money funnel
    captureEvent("ticket_cta_clicked", { evento_id: event.id, price: event.current_price || null });
    api.post("/tickets/click", { event_id: event.id }).catch(() => {});
  };

  const price = event.current_price;
  const ticketFriends = event.friends_with_ticket || [];
  const totalTickets = event.total_tickets || 0;
  const saleBadge = { pocas_entradas: "⚡ Pocas entradas", agotado: "🔒 Agotadas", a_la_venta: "🎟️ A la venta" }[event.sale_state];

  return (
    <div className="min-h-screen qv-app-bg">
      <div className="max-w-md mx-auto min-h-screen pb-10">
        {/* Hero */}
        <div className="relative h-72">
          {event.image_url ? (
            <img src={mediaThumb(event.image_url, 1200)} alt={event.name} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f]" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0C] via-[#0A0A0C]/50 to-transparent" />

          <button
            data-testid="detail-back"
            onClick={goBack}
            className="absolute top-6 left-4 w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <button
            data-testid="detail-follow"
            onClick={() => { if (requireAuth("recibir avisos de este plan")) setFollow.mutate(!event.is_following); }}
            className="absolute top-6 right-28 w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
            aria-label={t("event.aria_follow")}
          >
            <Bell className={`w-5 h-5 ${event.is_following ? "text-qv-secondary" : "text-white"}`} fill={event.is_following ? "currentColor" : "none"} />
          </button>
          {isAdmin && (
            <button
              data-testid="detail-admin-edit"
              onClick={openEdit}
              aria-label="Editar evento"
              className="absolute top-6 right-40 w-10 h-10 rounded-full qv-glass border border-qv-secondary/50 flex items-center justify-center text-qv-secondary active:scale-90 transition-transform"
            >
              <Pencil className="w-5 h-5" />
            </button>
          )}
          <button
            data-testid="detail-share-story"
            onClick={() => shareStory("neon")}
            disabled={storyBusy}
            aria-label="Compartir en Instagram Stories"
            className="absolute top-6 right-16 w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform disabled:opacity-60"
          >
            {storyBusy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Instagram className="w-5 h-5" />}
          </button>
          <button
            data-testid="detail-share"
            onClick={shareWhatsApp}
            className="absolute top-6 right-4 w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
          >
            <Send className="w-5 h-5" />
          </button>

          <div className="absolute bottom-0 w-full p-5">
            {event.genre && (
              <span className="qv-glass text-white text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border border-white/15">
                {event.genre}
              </span>
            )}
            <h1 className="font-display text-3xl font-black tracking-tighter text-white mt-2 leading-tight">
              {event.name}
            </h1>
          </div>
        </div>

        <div className="px-5 pt-4 flex flex-col gap-5">
          <div className="flex flex-col gap-2 text-white/80">
            <span className="flex items-center gap-2"><MapPin className="w-4 h-4 text-qv-secondary" /> {event.venue}{event.address ? ` · ${event.address}` : ""}</span>
            <span className="flex items-center gap-2 capitalize"><Clock className="w-4 h-4 text-qv-secondary" /> {formatPartyDate(event.date, event.time)}</span>
          </div>

          {/* Status */}
          {isPast ? (
            <button
              data-testid="detail-estuve-btn"
              onClick={() => toggle("estuve")}
              className={`h-12 rounded-2xl font-bold flex items-center justify-center gap-2 active:scale-95 transition-colors duration-150 ${
                isEstuve ? "bg-qv-primary text-white shadow-[0_0_20px_rgba(255,0,85,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
              }`}
            >
              {isEstuve ? <><CheckCircle2 className="w-5 h-5" /> {t("event.was_here")}</> : t("event.was_here")}
            </button>
          ) : !user ? (
            /* Sprint 3 — guest CTA stack (arrived from WhatsApp, not logged in).
               Primary = low-friction "Me interesa" (opens signup), tertiary =
               share back to WhatsApp. "Ver quién va" lives just below (teaser). */
            <div className="flex flex-col gap-2.5" data-testid="detail-guest-cta">
              <button
                data-testid="detail-guest-interesa"
                onClick={() => toggle("me_interesa")}
                className="qv-btn h-[52px] rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2 bg-qv-secondary text-[#06181a] shadow-[0_6px_18px_-8px_rgba(0,240,255,0.5)]"
              >
                <Eye className="w-5 h-5" /> {t("event.interested")}
              </button>
              <button
                data-testid="detail-guest-whatsapp"
                onClick={shareWhatsApp}
                className="qv-btn h-12 rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2 bg-white/[0.06] border border-white/12 text-white/80"
              >
                <Send className="w-4 h-4 text-[#25D366]" /> {t("event.share_whatsapp", "Compartir por WhatsApp")}
              </button>
            </div>
          ) : (
            <>
            <button
              data-testid="detail-propose-btn"
              onClick={() => openCreatePlan({ id: event.id, name: event.name, venue: event.venue, time: event.time, price: event.current_price, image_url: event.image_url, city: event.city }, event.city, "event")}
              className="qv-btn w-full h-[52px] rounded-2xl font-bold text-[15px] flex items-center justify-center gap-2 bg-white/[0.05] border border-qv-primary/45 text-white hover:bg-qv-primary/10 mb-3"
            >
              <ClipboardList className="w-5 h-5" /> {t("eventcard.btn_propose", "Proponer a mi grupo")}
            </button>
            <div className="grid grid-cols-2 gap-3">
              <button
                data-testid="detail-voy-btn"
                onClick={() => toggle("voy")}
                className={`qv-btn relative h-[52px] rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2 ${
                  isVoy
                    ? "bg-qv-primary text-white shadow-[0_6px_18px_-8px_rgba(255,0,85,0.55)]"
                    : "bg-white/[0.06] border border-white/12 text-white/80 hover:border-qv-primary/40"
                }`}
              >
                {isVoy && <Check className="w-5 h-5" />} {t("event.going")}
                {celebrateKey > 0 && <VoyCelebration key={celebrateKey} />}
              </button>
              <button
                data-testid="detail-interesa-btn"
                onClick={() => toggle("me_interesa")}
                className={`qv-btn h-[52px] rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2 ${
                  isInteresa
                    ? "bg-qv-secondary text-[#06181a] shadow-[0_6px_18px_-8px_rgba(0,240,255,0.5)]"
                    : "bg-white/[0.06] border border-white/12 text-white/80 hover:border-qv-secondary/40"
                }`}
              >
                {isInteresa ? <Star className="w-5 h-5" fill="currentColor" /> : <Eye className="w-5 h-5" />} {t("event.interested")}
              </button>
            </div>
            {/* Crowd counts — tap to see exactly who's going / interested. */}
            {(((event.going_count ?? 0) > 0) || ((event.interested_count ?? 0) > 0)) && (
              <div className="flex items-center gap-3 text-sm" data-testid="detail-crowd-counts">
                <button
                  data-testid="detail-count-going"
                  onClick={() => setPeopleSheet("voy")}
                  disabled={(event.going_count ?? 0) === 0}
                  className="flex items-center gap-1.5 text-white/70 active:scale-95 transition-transform disabled:opacity-50"
                >
                  <b className="text-white">{event.going_count ?? 0}</b> {t("event.count_going", "van")}
                </button>
                <span className="text-white/20">·</span>
                <button
                  data-testid="detail-count-interested"
                  onClick={() => setPeopleSheet("me_interesa")}
                  disabled={(event.interested_count ?? 0) === 0}
                  className="flex items-center gap-1.5 text-white/70 active:scale-95 transition-transform disabled:opacity-50"
                >
                  <b className="text-qv-secondary">{event.interested_count ?? 0}</b> {t("event.count_interested", "interesados")}
                </button>
              </div>
            )}
            {!isPast && (event.signups_today ?? 0) >= 2 && (
              <p
                data-testid="detail-signups-today"
                className="flex items-center gap-1.5 text-[12px] font-semibold text-emerald-300/90 leading-tight"
              >
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400/50 animate-ping" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                </span>
                {event.signups_today === 1
                  ? t("eventcard.signups_today_one")
                  : t("eventcard.signups_today_other", { count: event.signups_today })}
              </p>
            )}
            </>
          )}

          {!isPast && <EventOpenPlans eventId={event.id} />}

          {!isPast && (event.has_commission && event.commission_url ? (
            event.fv_embed_url ? (
              <FourvenuesEmbed
                embedUrl={event.fv_embed_url}
                fallbackUrl={event.commission_url}
                price={price}
                saleState={event.sale_state}
                onBuyClick={onTicketClick}
              />
            ) : (
            <div className="flex flex-col gap-2">
              <a
                data-testid="detail-ticket-btn"
                href={event.commission_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={onTicketClick}
                className={`qv-btn h-14 rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2 ${
                  event.sale_state === "agotado"
                    ? "bg-white/10 text-white/70 border border-white/20"
                    : "bg-qv-primary text-white shadow-[0_8px_22px_-10px_rgba(255,0,85,0.6)]"
                }`}
              >
                <Ticket className="w-5 h-5" />
                {event.sale_state === "agotado"
                  ? t("event.cta_soldout")
                  : event.sale_state === "solo_lista"
                  ? t("event.cta_list")
                  : t("event.cta_ticket")}
                {price ? <span className="opacity-90"> {t("event.price_from", { price: Math.round(price) })}</span> : null}
              </a>
              {saleBadge && (
                <p className={`text-center text-xs font-bold ${event.sale_state === "pocas_entradas" ? "text-yellow-300 animate-pulse" : "text-white/50"}`}>
                  {saleBadge}
                </p>
              )}
            </div>
            )
          ) : event.more_info_url ? (
            <a
              data-testid="detail-info-btn"
              href={event.more_info_url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-12 rounded-2xl bg-white/5 border border-white/20 text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform"
            >
              <ExternalLink className="w-5 h-5" /> {t("event.more_info")}
            </a>
          ) : null)}

          {/* "Ya tengo entrada" — social proof + conversion signal */}
          {!isPast && (
            <div className="flex items-center gap-3 rounded-2xl bg-white/[0.03] border border-white/10 p-3">
              <button
                data-testid="detail-ticket-owned-btn"
                onClick={() => { if (requireAuth("guardar tu entrada")) { const have = !event.my_has_ticket; if (have) captureEvent("i_have_ticket_marked", { evento_id: event.id }); setTicket.mutate(have); } }}
                className={`shrink-0 h-10 px-4 rounded-xl font-bold text-sm flex items-center justify-center gap-1.5 active:scale-95 transition-colors ${
                  event.my_has_ticket ? "bg-qv-secondary text-black" : "bg-white/10 text-white/80 border border-white/20"
                }`}
              >
                {event.my_has_ticket ? <><CheckCircle2 className="w-4 h-4" /> {t("event.have_ticket")}</> : <>{t("event.get_ticket_owned")}</>}
              </button>
              <div className="min-w-0 flex-1">
                {totalTickets > 0 ? (
                  <div className="flex items-center gap-2">
                    {ticketFriends.length > 0 && (
                      <div className="flex -space-x-2">
                        {ticketFriends.slice(0, 3).map((f, i) => (
                          <AvatarCircle key={i} name={f.name} picture={f.picture} size={22} />
                        ))}
                      </div>
                    )}
                    <p className="text-xs text-white/70 leading-tight">
                      {ticketFriends.length > 0
                        ? t("event.ticket_friends", { count: ticketFriends.length })
                        : t("event.ticket_total", { count: totalTickets })}
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-white/40 leading-tight">{t("event.ticket_first")}</p>
                )}
              </div>
            </div>
          )}

          {/* Compartir en Stories — sobrio, para difundir cada fiesta en Instagram */}
          {!isPast && (
            <button
              data-testid="detail-share-story-btn"
              onClick={() => shareStory("neon")}
              disabled={storyBusy}
              className="qv-btn h-12 rounded-2xl font-semibold text-[15px] flex items-center justify-center gap-2.5 bg-white/[0.06] border border-white/12 text-white/85 disabled:opacity-60"
            >
              <span className="flex items-center justify-center w-6 h-6 rounded-lg bg-gradient-to-br from-[#feda75] via-[#d62976] to-[#4f5bd5]">
                {storyBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin text-white" /> : <Instagram className="w-3.5 h-3.5 text-white" />}
              </span>
              {t("event.share_story", "Compartir en Stories")}
            </button>
          )}

          {/* Friends */}
          {user ? (
            <div className="flex flex-col gap-4">
              {isPast ? (
                <FriendRow title={t("event.friends_attended")} color="#FF0055" friends={event.friends_attended} />
              ) : (
                <>
                  <FriendRow title={t("event.friends_going")} color="#FF0055" friends={event.friends_going} />
                  <FriendRow title={t("event.friends_interested")} color="#00F0FF" friends={event.friends_interested} />
                </>
              )}
              {!isPast && (event.friends_going || []).length === 0 && (event.friends_interested || []).length === 0 && (
                <p className="text-white/55 text-sm" data-testid="detail-aggsocial">
                  {(() => {
                    const openPlans = event.open_plans_count || 0;
                    const nights = event.nights_at_venue || 0;
                    const going = event.going_count ?? event.total_going ?? 0;
                    const interested = event.interested_count ?? event.total_interested ?? 0;
                    if (openPlans > 0) {
                      return (
                        <span className="text-qv-primary font-semibold">
                          {t(openPlans === 1 ? "eventcard.open_plans_one" : "eventcard.open_plans_other", { count: openPlans })}
                        </span>
                      );
                    }
                    if ((going + interested) >= 5) {
                      return (
                        <span>
                          <b className="text-white/85">{going}</b> {t("eventcard.count_going", "van")}
                          <span className="text-white/25"> · </span>
                          <b className="text-white/75">{interested}</b> {t("eventcard.count_interested", "interesados")}
                        </span>
                      );
                    }
                    if (nights > 0) {
                      return <span>{t("eventcard.nights_at_venue", { count: nights, venue: event.venue })}</span>;
                    }
                    return <span className="text-white/45">{t("eventcard.new_this_week")}</span>;
                  })()}
                </p>
              )}
            </div>
          ) : (
            <button
              type="button"
              data-testid="detail-guest-friends"
              onClick={() => requireAuth("ver quién va")}
              className="w-full text-left rounded-2xl border border-qv-primary/40 bg-gradient-to-r from-qv-primary/15 to-qv-secondary/15 p-4 active:scale-[0.99]"
            >
              <p className="font-display font-black text-white">{t("event.guest_who")}</p>
              {!isPast && event.total_going > 0 ? (
                <div className="mt-3">
                  <BlurredGoingTeaser count={event.total_going} />
                </div>
              ) : (
                <p className="text-white/60 text-sm mt-1">{t("event.guest_sub")}</p>
              )}
            </button>
          )}

          {/* Repaso de la noche — shareable recap for past parties */}
          {user && isPast && <NightRecapCard event={event} />}

          {/* Noches en este sitio — past nights at the same venue */}
          <VenueNights eventId={event.id} venue={event.venue} />
          {/* Shared album — elevated so friends' photos don't get stuck in
              everyone's phone. Comes right after the friends block. */}
          {user && <EventAlbum eventId={event.id} hasInterest={hasInterest} prominent />}

          {/* El Momento — live during the party, and as a memory on past events */}
          {user && <EventMoment eventId={event.id} hasInterest={hasInterest} past={isPast} />}

          {/* Map + directions */}
          <div>
            <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2">{t("event.how_to_get")}</p>
            <div className="rounded-2xl overflow-hidden border border-white/10 h-48 bg-white/5">
              <iframe
                title={t("event.map")}
                data-testid="detail-map"
                src={`https://maps.google.com/maps?q=${mapQuery}&z=15&output=embed`}
                width="100%"
                height="100%"
                style={{ border: 0 }}
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
            <a
              data-testid="detail-directions"
              href={`https://www.google.com/maps/dir/?api=1&destination=${mapQuery}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 h-11 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95 transition-transform"
            >
              <Navigation className="w-4 h-4 text-qv-secondary" /> {t("event.how_to_get")}
            </a>
          </div>
        </div>
      </div>

      {/* Admin edit modal (pencil) */}
      {isAdmin && editOpen && form && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="admin-edit-modal">
          <form
            onSubmit={submitEdit}
            className="w-full max-w-md max-h-[92vh] overflow-y-auto qv-app-bg border border-white/15 rounded-t-3xl sm:rounded-3xl p-5 flex flex-col gap-4"
          >
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl font-black text-white">Editar evento</h2>
              <button type="button" onClick={() => setEditOpen(false)} data-testid="admin-edit-close" className="w-9 h-9 rounded-full bg-white/5 border border-white/15 flex items-center justify-center text-white active:scale-90">
                <X className="w-5 h-5" />
              </button>
            </div>

            {[
              { key: "name", label: "Nombre", placeholder: "Nombre del evento" },
              { key: "venue", label: "Discoteca / local", placeholder: "Nombre del local" },
              { key: "address", label: "Dirección", placeholder: "Dirección" },
              { key: "genre", label: "Género", placeholder: "Techno, Reggaeton…" },
              { key: "image_url", label: "Foto (URL)", placeholder: "https://…" },
              { key: "city", label: "Ciudad", placeholder: "Ibiza, Madrid…" },
            ].map((fld) => (
              <label key={fld.key} className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest font-bold text-white/50">{fld.label}</span>
                <input
                  data-testid={`admin-edit-${fld.key}`}
                  value={form[fld.key]}
                  onChange={(e) => setForm((f) => ({ ...f, [fld.key]: e.target.value }))}
                  placeholder={fld.placeholder}
                  className="h-11 rounded-xl bg-white/5 border border-white/15 px-3 text-white placeholder:text-white/30 focus:border-qv-secondary/60 outline-none"
                />
              </label>
            ))}

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest font-bold text-white/50">Fecha</span>
                <input type="date" data-testid="admin-edit-date" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} className="h-11 rounded-xl bg-white/5 border border-white/15 px-3 text-white outline-none focus:border-qv-secondary/60" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-widest font-bold text-white/50">Hora</span>
                <input type="time" data-testid="admin-edit-time" value={form.time} onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))} className="h-11 rounded-xl bg-white/5 border border-white/15 px-3 text-white outline-none focus:border-qv-secondary/60" />
              </label>
            </div>

            {/* Sticky buy-link override */}
            <div className="flex flex-col gap-1 pt-1 border-t border-white/10">
              <span className="text-[11px] uppercase tracking-widest font-bold text-qv-secondary mt-3">Enlace de compra (manual)</span>
              <input
                data-testid="admin-edit-link"
                value={form.link_override}
                onChange={(e) => setForm((f) => ({ ...f, link_override: e.target.value }))}
                placeholder="Déjalo vacío para usar el enlace automático"
                className="h-11 rounded-xl bg-white/5 border border-white/15 px-3 text-white placeholder:text-white/30 focus:border-qv-secondary/60 outline-none"
              />
              <p className="text-[11px] text-white/40 leading-snug mt-1">
                Si pones un enlace aquí, <b className="text-white/70">siempre manda el tuyo</b> (el scraper no lo tocará). Déjalo vacío para volver al automático.
              </p>
              {event.auto_commission_url && (
                <p className="text-[11px] text-white/40 break-all mt-1">
                  Enlace automático actual: <span className="text-white/60">{event.auto_commission_url}</span>
                </p>
              )}
              {(event.link_override || "").trim() && (
                <button type="button" onClick={resetLinkOverride} data-testid="admin-edit-reset-link" className="self-start mt-2 h-9 px-3 rounded-lg bg-white/5 border border-white/15 text-white/80 text-xs font-semibold flex items-center gap-1.5 active:scale-95">
                  <RotateCcw className="w-3.5 h-3.5" /> Volver a automático
                </button>
              )}
            </div>

            {/* Edit history + undo */}
            {editHistory?.edits?.length > 0 && (
              <div className="flex flex-col gap-2 pt-3 border-t border-white/10" data-testid="admin-edit-history">
                <span className="text-[11px] uppercase tracking-widest font-bold text-white/50">Historial de ediciones</span>
                <div className="flex flex-col gap-2 max-h-52 overflow-y-auto">
                  {editHistory.edits.map((h) => (
                    <div key={h.id} className="flex items-start gap-2 bg-white/5 border border-white/10 rounded-xl p-2.5" data-testid={`edit-log-${h.id}`}>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-white/80">
                          <b>{FIELD_LABELS[h.field] || h.field}</b>
                          {h.note === "undo" && <span className="ml-1 text-[10px] text-qv-secondary">(deshecho)</span>}
                        </p>
                        <p className="text-[11px] text-white/40 break-all">
                          {fmtEditVal(h.old_value)} <span className="text-white/30">→</span> {fmtEditVal(h.new_value)}
                        </p>
                        <p className="text-[10px] text-white/30 mt-0.5">
                          {h.by_name} · {new Date(h.created_at).toLocaleString("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                        </p>
                      </div>
                      <button
                        type="button"
                        data-testid={`edit-undo-${h.id}`}
                        onClick={() => undoEdit.mutate(h.id)}
                        disabled={undoEdit.isPending}
                        title="Deshacer este cambio"
                        className="shrink-0 h-8 px-2.5 rounded-lg bg-white/5 border border-white/15 text-white/80 text-[11px] font-semibold flex items-center gap-1 active:scale-95 disabled:opacity-50"
                      >
                        <RotateCcw className="w-3.5 h-3.5" /> Deshacer
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              type="submit"
              data-testid="admin-edit-save"
              disabled={saveEdit.isPending}
              className="h-12 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60 mt-1"
            >
              {saveEdit.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : "Guardar cambios"}
            </button>
          </form>
        </div>
      )}

      {/* People sheet — who's going / interested (Sprint 2 reciprocity) */}
      {user && peopleSheet && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm"
          data-testid="people-sheet"
          onClick={() => setPeopleSheet(null)}
        >
          <div
            className="w-full max-w-md max-h-[80vh] overflow-y-auto qv-app-bg border border-white/15 rounded-t-3xl sm:rounded-3xl p-5 flex flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl font-black text-white flex items-center gap-2">
                {peopleSheet === "voy"
                  ? <><Users className="w-5 h-5 text-qv-primary" /> {t("event.count_going", "van")}</>
                  : <><Eye className="w-5 h-5 text-qv-secondary" /> {t("event.count_interested", "interesados")}</>}
                <span className="text-white/40 font-bold">{peopleData?.count ?? ""}</span>
              </h2>
              <button
                type="button"
                data-testid="people-sheet-close"
                onClick={() => setPeopleSheet(null)}
                className="w-9 h-9 rounded-full bg-white/5 border border-white/15 flex items-center justify-center text-white active:scale-90"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {peopleLoading ? (
              <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
            ) : (peopleData?.people || []).length === 0 ? (
              <p className="text-white/40 text-sm py-6 text-center">{t("event.people_empty", "Aún nadie por aquí")}</p>
            ) : (
              <div className="flex flex-col gap-2">
                {peopleData.people.map((p) => (
                  <button
                    key={p.user_id}
                    type="button"
                    onClick={() => { if (!p.is_me) { setPeopleSheet(null); navigate(`/users/${p.user_id}`); } }}
                    className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-2.5 text-left active:scale-[0.99] transition-transform"
                    data-testid={`people-row-${p.user_id}`}
                  >
                    <AvatarCircle name={p.name} picture={p.picture} size={40} ring={p.is_friend} />
                    <div className="min-w-0 flex-1">
                      <span className="font-semibold text-sm text-white block truncate">
                        {p.is_me ? t("eventcard.you", "Tú") : p.name}
                      </span>
                      {p.is_friend && !p.is_me && (
                        <span className="text-[11px] text-qv-primary font-semibold">{t("event.people_friend", "Amigo")}</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
