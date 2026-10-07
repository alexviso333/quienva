import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { Ticket, ExternalLink, MapPin, Clock, Check, Star, Send, CheckCircle2, Info, Bell, BellOff, Flame, Lock, ClipboardList, Euro, Eye } from "lucide-react";
import { AvatarCircle } from "@/components/AvatarCircle";
import { BlurredGoingTeaser } from "@/components/BlurredGoingTeaser";
import { VoyCelebration } from "@/components/VoyCelebration";
import api, { mediaThumb, API } from "@/lib/api";
import { useCreatePlan } from "@/context/CreatePlan";
import { formatPartyDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";
import { toast } from "@/lib/notify";
import { useTranslation } from "react-i18next";
import { captureEvent } from "@/analytics/posthog";
import { MovingBadge } from "@/components/MovingNow";

// Builds "Marta" / "Marta y 2 más" for a friends list.
function namesList(t, friends) {
  const first = friends[0].name.split(" ")[0];
  if (friends.length === 1) return t("eventcard.names_one", { name: first });
  return t("eventcard.names_other", { name: first, count: friends.length - 1 });
}

// Social proof sentence for going / interested, including the current user.
function socialText(t, friends, isMe, ctx) {
  const count = friends.length + (isMe ? 1 : 0);
  if (count === 0) return null;
  if (isMe && friends.length === 0) return t(`eventcard.${ctx}.you`);
  if (isMe) return t(`eventcard.${ctx}.you_plus`, { count: friends.length });
  const first = friends[0].name.split(" ")[0];
  if (friends.length === 1) return t(`eventcard.${ctx}.one`, { name: first });
  return t(`eventcard.${ctx}.other`, { name: first, count: friends.length - 1 });
}

// "Marta estuvo" / "Marta y 2 estuvieron" for a past attended list.
function attendedText(t, attended) {
  const first = attended[0].name.split(" ")[0];
  if (attended.length === 1) return t("eventcard.attended_one", { name: first });
  return t("eventcard.attended_other", { name: first, count: attended.length - 1 });
}

const todayStr = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
};

// FOMO countdown: returns a short "starts in X" label only when the party is
// imminent (< 12h), so the urgency is real and not spammy. Uses the event start
// time when available, otherwise assumes a night-time (23:00) start.
function startCountdown(dateStr, timeStr) {
  if (!dateStr) return null;
  const [y, m, d] = dateStr.split("-").map(Number);
  if (!y || !m || !d) return null;
  let hh = 23, mm = 0;
  const tm = (timeStr || "").match(/(\d{1,2}):(\d{2})/);
  if (tm) { hh = +tm[1]; mm = +tm[2]; }
  const start = new Date(y, m - 1, d, hh, mm);
  const diffMs = start.getTime() - Date.now();
  if (diffMs <= 0) return null;
  const totalMin = Math.floor(diffMs / 60000);
  if (totalMin > 12 * 60) return null; // only surface urgency within 12h
  const h = Math.floor(totalMin / 60);
  const mnt = totalMin % 60;
  return h >= 1 ? `${h}h ${mnt}m` : `${mnt}m`;
}

const SALE_STATE_META = {
  no_a_la_venta: { cls: "bg-white/10 text-white/70", icon: Clock },
  a_la_venta:    { cls: "bg-emerald-400/20 text-emerald-300", icon: Ticket },
  pocas_entradas:{ cls: "bg-orange-400/25 text-orange-200", icon: Flame },
  agotado:       { cls: "bg-white/10 text-white/50", icon: Lock },
  solo_lista:    { cls: "bg-violet-400/20 text-violet-200", icon: ClipboardList },
};

function PriceBadge({ event }) {
  const { t } = useTranslation();
  const state = event.sale_state || "no_a_la_venta";
  const meta = SALE_STATE_META[state] || SALE_STATE_META.no_a_la_venta;
  const Icon = meta.icon;
  const price = event.current_price;
  const currency = event.currency || "EUR";
  const symbol = currency === "EUR" ? "€" : currency;
  if (!price && state === "no_a_la_venta") return null;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full backdrop-blur-sm ${meta.cls}`}>
      <Icon className="w-3 h-3" />
      {price ? `${Math.round(price)}${symbol}` : ""}
      {price && state !== "no_a_la_venta" ? " · " : ""}
      {t(`eventcard.sale.${state}`)}
    </span>
  );
}

export function EventCard({ event, index = 0, onSetStatus, pending, highlight, cardRef }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { requireAuth } = useGuestGate();
  const { open: openCreatePlan } = useCreatePlan();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const prefersReduced = useReducedMotion();
  const [celebrateKey, setCelebrateKey] = useState(0);
  const isPast = event.date < todayStr();
  const going = event.friends_going || [];
  const interested = event.friends_interested || [];
  const attended = event.friends_attended || [];
  const countdown = !isPast ? startCountdown(event.date, event.time) : null;

  const isVoy = event.my_status === "voy";
  const isInteresa = event.my_status === "me_interesa";
  const isEstuve = event.my_status === "estuve";
  const isFollowing = !!event.is_following;

  // Toggle follow — optimistic update, then invalidate.
  const toggleFollow = useMutation({
    mutationFn: async () => {
      if (isFollowing) return (await api.delete(`/events/${event.id}/follow`)).data;
      return (await api.post(`/events/${event.id}/follow`)).data;
    },
    onSuccess: (d) => {
      toast.success(d.following ? t("eventcard.follow_on") : t("eventcard.follow_off"));
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
      qc.invalidateQueries({ queryKey: ["top-weekend"] });
    },
    onError: () => toast.error(t("eventcard.toast_error")),
  });

  // Build preview list including "yo" if I'm going/interested/attended
  const meEntry = user ? { user_id: "me", name: t("eventcard.you"), picture: user.picture || "" } : null;
  const previewGoing = isVoy && meEntry ? [meEntry, ...going] : going;
  const previewInteresa = isInteresa && meEntry ? [meEntry, ...interested] : interested;
  const previewAttended = isEstuve && meEntry ? [meEntry, ...attended] : attended;
  const previewFriends = (isPast ? previewAttended : [...previewGoing, ...previewInteresa]).slice(0, 4);

  const goingText = socialText(t, going, isVoy, "going");
  const interestedText = socialText(t, interested, isInteresa, "interested");

  const toggle = (status) => {
    const next = event.my_status === status ? "none" : status;
    if (status === "voy" && next === "voy") setCelebrateKey((k) => k + 1);
    if (next === "voy") captureEvent("event_going", { evento_id: event.id });
    else if (next === "me_interesa") captureEvent("event_interested", { evento_id: event.id });
    onSetStatus(event.id, next);
  };

  const shareWhatsApp = (e) => {
    if (e) e.stopPropagation();
    captureEvent("event_share", { evento_id: event.id, destination: "whatsapp" });
    // Share the backend public landing. The landing renders OG tags so
    // WhatsApp/Instagram embed a rich card AND lets non-registered viewers
    // see the party + 👁 views + "Comprar entrada" without hitting the SPA
    // auth wall. Registered users can still tap "Abrir en la app" at the
    // bottom of the landing.
    const link = `${API}/e/${event.id}`;
    const text = `${event.name} — ¿vienes? 👀\n${link}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
  };

  return (
    <motion.article
      ref={cardRef}
      data-testid={`event-card-${event.id}`}
      initial={prefersReduced ? false : { opacity: 0, y: 26, scale: 0.985 }}
      whileInView={prefersReduced ? undefined : { opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true, margin: "-60px" }}
      whileHover={prefersReduced ? undefined : { y: -6 }}
      transition={{ duration: 0.5, delay: Math.min(index * 0.06, 0.28), ease: [0.16, 1, 0.3, 1] }}
      className={`group relative rounded-[26px] p-[1.5px] transition-[background,box-shadow] duration-500 bg-gradient-to-br ${
        highlight
          ? "from-qv-secondary via-qv-secondary/40 to-qv-primary shadow-[0_0_0_1px_rgba(0,240,255,0.5),0_22px_60px_-18px_rgba(0,240,255,0.45)]"
          : "from-white/15 via-white/[0.05] to-white/10 shadow-[0_10px_34px_-16px_rgba(0,0,0,0.9)] hover:from-qv-primary/60 hover:via-white/10 hover:to-qv-secondary/55 hover:shadow-[0_26px_70px_-20px_rgba(255,0,85,0.4)]"
      }`}
    >
     <div className="relative rounded-[25px] overflow-hidden bg-[#0e0e12]">
      {/* subtle top gloss highlight */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent z-20" />
      {/* Image banner */}
      <div
        className="relative h-52 lg:h-56 cursor-pointer overflow-hidden"
        onClick={() => navigate(`/event/${event.id}`)}
        data-testid={`event-open-${event.id}`}
      >
        {event.image_url ? (
          <img src={mediaThumb(event.image_url, 900)} alt={event.name} className="w-full h-full object-cover transform-gpu will-change-transform transition-transform duration-[900ms] ease-out group-hover:scale-[1.07]" loading="lazy" />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f]" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-[#0e0e12] via-[#0e0e12]/55 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-transparent" />
        {/* hover neon sheen — opacity-only, GPU friendly */}
        <div className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-[radial-gradient(120%_80%_at_50%_0%,rgba(255,0,85,0.2),transparent_60%)]" />

        <div className="absolute top-3 left-3 flex flex-col gap-1.5 items-start">
            {!isPast && <MovingBadge event={event} />}
            {event.is_affiliate && (
              <span
                data-testid={`event-affiliate-${event.id}`}
                title={t("eventcard.badge_mylink_title")}
                className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full bg-gradient-to-r from-lime-300 to-green-500 text-black flex items-center gap-1 shadow-[0_0_14px_rgba(132,204,22,0.6)]"
              >
                <Euro className="w-3 h-3" /> {t("eventcard.badge_mylink")}
              </span>
            )}
            {event.featured && (
              <span
                data-testid={`event-featured-${event.id}`}
                className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full bg-gradient-to-r from-yellow-300 to-amber-400 text-black flex items-center gap-1 shadow-[0_0_14px_rgba(253,224,71,0.5)]"
              >
                <Star className="w-3 h-3" fill="currentColor" /> {t("eventcard.badge_featured")}
              </span>
            )}
            {event.genre && (
              <span
                data-testid={`event-genre-${event.id}`}
                className="qv-glass text-white text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border border-white/15"
              >
                {event.genre}
              </span>
            )}
            <PriceBadge event={event} />
            {countdown && (
              <span
                data-testid={`event-countdown-${event.id}`}
                className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-wider px-2 py-1 rounded-full bg-qv-primary/90 text-white shadow-[0_0_14px_rgba(255,0,85,0.55)] animate-pulse"
              >
                <Clock className="w-3 h-3" /> {t("eventcard.starts_in", "Empieza en")} {countdown}
              </span>
            )}
        </div>

        <div className="absolute top-3 right-3 flex items-center gap-1.5">
          {!isPast && (
            <button
              data-testid={`event-follow-btn-${event.id}`}
              onClick={(e) => { e.stopPropagation(); toggleFollow.mutate(); }}
              disabled={toggleFollow.isPending}
              aria-label={isFollowing ? t("eventcard.aria_follow_on") : t("eventcard.aria_follow_off")}
              className={`w-8 h-8 rounded-full border flex items-center justify-center active:scale-90 transition-transform ${
                isFollowing
                  ? "bg-qv-secondary text-black border-qv-secondary shadow-[0_0_14px_rgba(0,240,255,0.5)]"
                  : "qv-glass text-white border-white/15"
              }`}
            >
              {isFollowing ? <Bell className="w-4 h-4" fill="currentColor" /> : <Bell className="w-4 h-4" />}
            </button>
          )}
          <button
            data-testid={`event-share-btn-${event.id}`}
            onClick={shareWhatsApp}
            aria-label={t("eventcard.aria_share")}
            className="w-8 h-8 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>

        <div className="absolute bottom-0 w-full p-4 z-10">
          <h2 className="font-display text-xl lg:text-[22px] font-black tracking-tight text-white leading-[1.05] line-clamp-2 drop-shadow-[0_2px_10px_rgba(0,0,0,0.6)]">
            {event.name}
          </h2>
          <div className="flex items-center gap-2 text-white/75 text-xs mt-1.5 font-medium">
            <span className="flex items-center gap-1 min-w-0">
              <MapPin className="w-3.5 h-3.5 text-qv-secondary shrink-0" />
              <span className="truncate">{event.venue}</span>
            </span>
            <span className="w-1 h-1 rounded-full bg-white/30 shrink-0" />
            <span className="flex items-center gap-1 shrink-0">
              <Clock className="w-3.5 h-3.5" /> {formatPartyDate(event.date, event.time)}
            </span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 flex flex-col gap-3">
        {/* Social proof — core value */}
        <div className="flex items-center gap-2.5 min-h-[34px]" data-testid={`event-social-${event.id}`}>
          {!user && !isPast && event.total_going > 0 ? (
            <BlurredGoingTeaser
              count={event.total_going}
              onClick={(e) => { e.stopPropagation(); requireAuth(t("eventcard.reason_going")); }}
            />
          ) : previewFriends.length > 0 ? (
            <>
              <div className="flex -space-x-2.5 shrink-0">
                {previewFriends.map((f, i) => (
                  <button
                    key={f.user_id + i}
                    onClick={(e) => { e.stopPropagation(); if (f.user_id && f.user_id !== "me") navigate(`/users/${f.user_id}`); }}
                    className="rounded-full active:scale-90 transition-transform"
                  >
                    <AvatarCircle name={f.name} picture={f.picture} size={30} />
                  </button>
                ))}
              </div>
              <p className="text-xs text-white/85 leading-tight">
                {isPast ? (
                  isEstuve && attended.length > 0 ? (
                    <span className="font-semibold text-white">{t("eventcard.matched_with", { names: namesList(t, attended) })}</span>
                  ) : isEstuve ? (
                    <span className="font-semibold text-white">{t("eventcard.were_here")}</span>
                  ) : (
                    <span className="font-semibold text-white">{attendedText(t, attended)}</span>
                  )
                ) : (
                  <>
                    {goingText && (
                      <span className="block">
                        <span className="text-qv-primary">●</span> <span className="font-semibold text-white">{goingText}</span>
                      </span>
                    )}
                    {interestedText && (
                      <span className="block text-white/60">
                        <span className="text-qv-secondary">●</span> {interestedText}
                      </span>
                    )}
                  </>
                )}
              </p>
            </>
          ) : !isPast ? (
            <p className="text-xs text-white/60 leading-tight" data-testid={`event-aggsocial-${event.id}`}>
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
                      <b className="text-white/80">{going}</b> {t("eventcard.count_going", "van")}
                      <span className="text-white/25"> · </span>
                      <b className="text-white/70">{interested}</b> {t("eventcard.count_interested", "interesados")}
                    </span>
                  );
                }
                if (nights > 0) {
                  return <span>{t("eventcard.nights_at_venue", { count: nights, venue: event.venue })}</span>;
                }
                return <span className="text-white/45">{t("eventcard.new_this_week")}</span>;
              })()}
            </p>
          ) : null}
        </div>

        {/* Crowd counts — separated intent signal ("17 van · 42 interesados"),
            never summed. Shown whenever there is any real activity.
            Append also the public view count (👁) when ≥ 20 so there's gentle
            social proof on new events without screaming "1 persona lo vio". */}
        {!isPast && (((event.going_count ?? event.total_going ?? 0) > 0) || ((event.interested_count ?? event.total_interested ?? 0) > 0) || (event.view_count ?? 0) > 0) && (
          <p className="text-[11px] text-white/45 -mt-1 leading-tight flex items-center flex-wrap gap-x-1" data-testid={`event-counts-${event.id}`}>
            {((event.going_count ?? event.total_going ?? 0) > 0) && (
              <>
                <b className="text-white/80">{event.going_count ?? event.total_going ?? 0}</b> {t("eventcard.count_going", "van")}
              </>
            )}
            {((event.going_count ?? event.total_going ?? 0) > 0) && ((event.interested_count ?? event.total_interested ?? 0) > 0) && (
              <span className="text-white/25"> · </span>
            )}
            {((event.interested_count ?? event.total_interested ?? 0) > 0) && (
              <>
                <b className="text-white/70">{event.interested_count ?? event.total_interested ?? 0}</b> {t("eventcard.count_interested", "interesados")}
              </>
            )}
            {(event.view_count ?? 0) > 0 && (
              <span
                data-testid={`event-views-${event.id}`}
                className="inline-flex items-center gap-1 text-white/40"
                title={t("eventcard.views_title", "Personas que han visto este evento")}
              >
                {((event.going_count ?? event.total_going ?? 0) > 0 || (event.interested_count ?? event.total_interested ?? 0) > 0) ? <span className="text-white/25"> · </span> : null}
                <Eye className="w-3 h-3" />
                <b className="text-white/60">{event.view_count}</b>
              </span>
            )}
          </p>
        )}

        {/* Urgencia en vivo: cuánta gente se ha apuntado hoy (solo si es relevante) */}
        {!isPast && (event.signups_today ?? 0) >= 2 && (
          <p
            data-testid={`event-signups-today-${event.id}`}
            className="flex items-center gap-1.5 -mt-0.5 text-[11px] font-semibold text-emerald-300/90 leading-tight"
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

        {/* FOMO: friends are going and you are not (only when there's real social pressure) */}
        {!isPast && !isVoy && going.length >= 2 && (
          <button
            data-testid={`event-friends-fomo-${event.id}`}
            onClick={() => { if (!requireAuth(t("eventcard.reason_going"))) return; toggle("voy"); }}
            className="w-full text-left rounded-xl border border-qv-primary/40 bg-gradient-to-r from-qv-primary/15 to-transparent px-3 py-2 flex items-center gap-2 active:scale-[0.99] transition-transform"
          >
            <Flame className="w-4 h-4 text-qv-primary shrink-0" />
            <span className="text-xs text-white leading-tight">
              <b>{namesList(t, going)}</b> {t("eventcard.friends_fomo", "van y t\u00fa no. \u00bfTe lo vas a perder?")}
            </span>
          </button>
        )}

        {/* Actions */}
        {isPast ? (
          <button
            data-testid={`event-estuve-btn-${event.id}`}
            disabled={pending}
            onClick={() => toggle("estuve")}
            className={`h-11 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-150 active:scale-95 ${
              isEstuve
                ? "bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]"
                : "bg-white/[0.06] border border-white/15 text-white/80 hover:border-qv-primary/50 hover:bg-qv-primary/10"
            }`}
          >
            {isEstuve ? <><CheckCircle2 className="w-4 h-4" /> {t("eventcard.btn_was_here")}</> : t("eventcard.btn_was_here")}
          </button>
        ) : (
          <>
            {/* 1) Revenue-first: buy ticket is the primary CTA whenever available */}
            {event.has_commission && event.commission_url ? (
              <a
                data-testid={`event-ticket-btn-${event.id}`}
                href={event.commission_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => { captureEvent("ticket_cta_clicked", { evento_id: event.id, price: event.current_price || null }); api.post("/tickets/click", { event_id: event.id }).catch(() => {}); }}
                className="qv-btn h-12 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]"
              >
                <Ticket className="w-4 h-4" /> {t("eventcard.btn_ticket")}{event.current_price ? ` · ${t("event.price_from", { price: Math.round(event.current_price) })}` : ""}
              </a>
            ) : null}

            {/* 2) Engagement: propose a plan. Primary gradient when there's no ticket, clear secondary otherwise. */}
            <button
              data-testid={`event-propose-btn-${event.id}`}
              onClick={(e) => { e.stopPropagation(); openCreatePlan({ id: event.id, name: event.name, venue: event.venue, time: event.time, price: event.current_price, image_url: event.image_url, city: event.city }, event.city, "event"); }}
              className={`qv-btn h-11 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 ${
                event.has_commission && event.commission_url
                  ? "bg-white/[0.05] border border-qv-primary/45 text-white hover:bg-qv-primary/10"
                  : "bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]"
              }`}
            >
              <ClipboardList className="w-4 h-4" /> {t("eventcard.btn_propose", "Proponer a mi grupo")}
            </button>

            <div className="grid grid-cols-2 gap-2.5">
              <button
                data-testid={`event-voy-btn-${event.id}`}
                disabled={pending}
                onClick={() => toggle("voy")}
                className={`qv-btn relative h-11 rounded-2xl font-semibold text-sm flex items-center justify-center gap-1.5 ${
                  isVoy
                    ? "bg-qv-primary text-white shadow-[0_6px_16px_-8px_rgba(255,0,85,0.55)]"
                    : "bg-white/[0.06] border border-white/12 text-white/80 hover:border-qv-primary/40"
                }`}
              >
                {isVoy && <Check className="w-4 h-4" />} {t("eventcard.btn_going")}
                {celebrateKey > 0 && <VoyCelebration key={celebrateKey} />}
              </button>
              <button
                data-testid={`event-interesa-btn-${event.id}`}
                disabled={pending}
                onClick={() => toggle("me_interesa")}
                className={`qv-btn h-11 rounded-2xl font-semibold text-sm flex items-center justify-center gap-1.5 ${
                  isInteresa
                    ? "bg-qv-secondary text-[#06181a] shadow-[0_6px_16px_-8px_rgba(0,240,255,0.5)]"
                    : "bg-white/[0.06] border border-white/12 text-white/80 hover:border-qv-secondary/40"
                }`}
              >
                {isInteresa ? <Star className="w-4 h-4" fill="currentColor" /> : <Eye className="w-4 h-4" />} {t("eventcard.btn_interested")}
              </button>
            </div>

            <p className="flex items-center gap-1.5 text-[10.5px] text-white/40 leading-tight pl-0.5">
              <Info className="w-3 h-3 shrink-0" />
              <span><b className="text-white/60">{t("eventcard.voy_word")}</b> {t("eventcard.eq_confirmed")} · <b className="text-white/60">{t("eventcard.interesa_word")}</b> {t("eventcard.eq_notify")}</span>
            </p>

            {!(event.has_commission && event.commission_url) && event.more_info_url ? (
              <a
                data-testid={`event-info-btn-${event.id}`}
                href={event.more_info_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-white/50 hover:text-white/80 transition-colors mx-auto py-1"
              >
                <ExternalLink className="w-3.5 h-3.5" /> {t("eventcard.btn_more_info")}
              </a>
            ) : null}
          </>
        )}
      </div>
     </div>
    </motion.article>
  );
}
