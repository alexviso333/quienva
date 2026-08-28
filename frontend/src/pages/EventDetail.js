import { useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb, API } from "@/lib/api";
import { formatPartyDate } from "@/lib/format";
import { AvatarCircle } from "@/components/AvatarCircle";
import { BlurredGoingTeaser } from "@/components/BlurredGoingTeaser";
import { EventAlbum } from "@/components/EventAlbum";
import { EventMoment } from "@/components/EventMoment";
import FourvenuesEmbed from "@/components/FourvenuesEmbed";
import { NightRecapCard } from "@/components/NightRecapCard";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";
import {
  ArrowLeft, MapPin, Clock, Ticket, ExternalLink, Send, Check, Star, Navigation, CheckCircle2, Loader2, Bell, Instagram, Pencil, X, RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

const todayStr = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
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
  const navigate = useNavigate();
  const [storyBusy, setStoryBusy] = useState(false);
  const isAdmin = user?.role === "admin";
  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState(null);
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
    // A genuine 404 (party removed/rescheduled) must NOT retry — show the
    // friendly "no longer available" screen immediately instead of hanging.
    retry: (count, err) => (err?.response?.status === 404 ? false : count < 2),
  });

  const setStatus = useMutation({
    mutationFn: async (status) => (await api.post(`/events/${id}/interest`, { status })).data,
    onMutate: async (status) => {
      await qc.cancelQueries({ queryKey: ["event", id] });
      const prev = qc.getQueryData(["event", id]);
      qc.setQueryData(["event", id], (e) => (e ? { ...e, my_status: status } : e));
      const patchArr = (arr) =>
        Array.isArray(arr) ? arr.map((e) => (e.id === id ? { ...e, my_status: status } : e)) : arr;
      qc.getQueriesData({ queryKey: ["events"] }).forEach(([key, data]) => {
        qc.setQueryData(key, patchArr(data));
      });
      return { prev };
    },
    onSuccess: (_d, status) => {
      if (status === "voy") toast.success(t("event.toast_going"));
      if (status === "estuve") toast.success(t("event.toast_saved"));
    },
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
    },
    onError: () => toast.error("No se pudo guardar"),
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
    setStatus.mutate(event.my_status === s ? "none" : s);
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
              className={`h-12 rounded-2xl font-bold flex items-center justify-center gap-2 active:scale-95 transition-colors duration-300 ${
                isEstuve ? "bg-qv-primary text-white shadow-[0_0_20px_rgba(255,0,85,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
              }`}
            >
              {isEstuve ? <><CheckCircle2 className="w-5 h-5" /> {t("event.was_here")}</> : t("event.was_here")}
            </button>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <button
                data-testid="detail-voy-btn"
                onClick={() => toggle("voy")}
                className={`h-12 rounded-2xl font-bold flex items-center justify-center gap-2 active:scale-95 transition-colors duration-300 ${
                  isVoy ? "bg-qv-primary text-white shadow-[0_0_20px_rgba(255,0,85,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
                }`}
              >
                {isVoy && <Check className="w-5 h-5" />} {t("event.going")}
              </button>
              <button
                data-testid="detail-interesa-btn"
                onClick={() => toggle("me_interesa")}
                className={`h-12 rounded-2xl font-bold flex items-center justify-center gap-2 active:scale-95 transition-colors duration-300 ${
                  isInteresa ? "bg-qv-secondary text-black shadow-[0_0_20px_rgba(0,240,255,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
                }`}
              >
                {isInteresa && <Star className="w-5 h-5" />} {t("event.interested")}
              </button>
            </div>
          )}

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
                className={`h-14 rounded-2xl font-display font-black text-base flex items-center justify-center gap-2 active:scale-95 transition-transform ${
                  event.sale_state === "agotado"
                    ? "bg-white/10 text-white/70 border border-white/20"
                    : "bg-gradient-to-r from-qv-primary to-qv-secondary text-black shadow-[0_0_24px_rgba(255,0,85,0.35)]"
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
                onClick={() => { if (requireAuth("guardar tu entrada")) setTicket.mutate(!event.my_has_ticket); }}
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
              {((isPast && (event.friends_attended || []).length === 0) ||
                (!isPast && (event.friends_going || []).length === 0 && (event.friends_interested || []).length === 0)) && (
                <p className="text-white/40 text-sm italic" data-testid="detail-nofriends">
                  {t("event.no_friends")}
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

    </div>
  );
}
