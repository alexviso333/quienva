import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { Ticket, ExternalLink, MapPin, Clock, Check, Star, Send, CheckCircle2, Info, Bell, BellOff, Flame, Lock, ClipboardList, Euro } from "lucide-react";
import { AvatarCircle } from "@/components/AvatarCircle";
import { BlurredGoingTeaser } from "@/components/BlurredGoingTeaser";
import api, { mediaThumb, API } from "@/lib/api";
import { formatPartyDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const qc = useQueryClient();
  const prefersReduced = useReducedMotion();
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

  const toggle = (status) => onSetStatus(event.id, event.my_status === status ? "none" : status);

  const shareWhatsApp = (e) => {
    if (e) e.stopPropagation();
    // Share the backend OG page so WhatsApp renders a compact card with the
    // party poster instead of a long, spammy text line.
    const link = `${API}/share/event/${event.id}`;
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
          ) : (
            <p className="text-xs text-white/40 italic" data-testid={`event-nofriends-${event.id}`}>
              {isPast ? t("eventcard.nofriends_past") : t("eventcard.nofriends_future")}
            </p>
          )}
        </div>

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
            className={`h-11 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 transition-all duration-300 active:scale-95 ${
              isEstuve
                ? "bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]"
                : "bg-white/[0.06] border border-white/15 text-white/80 hover:border-qv-primary/50 hover:bg-qv-primary/10"
            }`}
          >
            {isEstuve ? <><CheckCircle2 className="w-4 h-4" /> {t("eventcard.btn_was_here")}</> : t("eventcard.btn_was_here")}
          </button>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                data-testid={`event-voy-btn-${event.id}`}
                disabled={pending}
                onClick={() => toggle("voy")}
                className={`h-11 rounded-2xl font-bold text-sm flex items-center justify-center gap-1.5 transition-all duration-300 active:scale-95 ${
                  isVoy
                    ? "bg-gradient-to-r from-qv-primary to-[#ff3d7f] text-white shadow-[0_8px_22px_-6px_rgba(255,0,85,0.6)]"
                    : "bg-white/[0.06] border border-white/15 text-white/85 hover:border-qv-primary/50 hover:bg-qv-primary/10"
                }`}
              >
                {isVoy && <Check className="w-4 h-4" />} {t("eventcard.btn_going")}
              </button>
              <button
                data-testid={`event-interesa-btn-${event.id}`}
                disabled={pending}
                onClick={() => toggle("me_interesa")}
                className={`h-11 rounded-2xl font-bold text-sm flex items-center justify-center gap-1.5 transition-all duration-300 active:scale-95 ${
                  isInteresa
                    ? "bg-gradient-to-r from-qv-secondary to-[#4df3ff] text-black shadow-[0_8px_22px_-6px_rgba(0,240,255,0.6)]"
                    : "bg-white/[0.06] border border-white/15 text-white/85 hover:border-qv-secondary/50 hover:bg-qv-secondary/10"
                }`}
              >
                {isInteresa && <Star className="w-4 h-4" />} {t("eventcard.btn_interested")}
              </button>
            </div>

            <p className="flex items-center gap-1.5 text-[10.5px] text-white/40 leading-tight pl-0.5">
              <Info className="w-3 h-3 shrink-0" />
              <span><b className="text-white/60">{t("eventcard.voy_word")}</b> {t("eventcard.eq_confirmed")} · <b className="text-white/60">{t("eventcard.interesa_word")}</b> {t("eventcard.eq_notify")}</span>
            </p>

            {event.has_commission && event.commission_url ? (
              <a
                data-testid={`event-ticket-btn-${event.id}`}
                href={event.commission_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => api.post("/tickets/click", { event_id: event.id }).catch(() => {})}
                className="group/tk relative h-11 rounded-2xl overflow-hidden text-black font-bold text-sm flex items-center justify-center gap-2 transition-transform duration-300 hover:-translate-y-0.5 active:scale-95 bg-gradient-to-r from-qv-primary via-[#ff5fa2] to-qv-secondary shadow-[0_10px_26px_-8px_rgba(255,0,85,0.5)]"
              >
                <span className="pointer-events-none absolute inset-0 -translate-x-full group-hover/tk:translate-x-full transition-transform duration-700 bg-gradient-to-r from-transparent via-white/40 to-transparent" />
                <Ticket className="w-4 h-4" /> {t("eventcard.btn_ticket")}{event.current_price ? ` · ${Math.round(event.current_price)}€` : ""}
              </a>
            ) : event.more_info_url ? (
              <a
                data-testid={`event-info-btn-${event.id}`}
                href={event.more_info_url}
                target="_blank"
                rel="noopener noreferrer"
                className="h-11 rounded-2xl bg-white/[0.06] border border-white/15 text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-300 hover:border-white/30 active:scale-95"
              >
                <ExternalLink className="w-4 h-4" /> {t("eventcard.btn_more_info")}
              </a>
            ) : null}
          </>
        )}
      </div>
     </div>
    </motion.article>
  );
}
