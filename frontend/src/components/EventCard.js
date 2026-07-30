import { motion } from "framer-motion";
import { Ticket, ExternalLink, MapPin, Clock, Check, Star } from "lucide-react";
import { AvatarCircle } from "@/components/AvatarCircle";
import { mediaUrl } from "@/lib/api";

function friendsText(friends, verb) {
  if (!friends || friends.length === 0) return null;
  const first = friends[0].name.split(" ")[0];
  if (friends.length === 1) return `${first} ${verb}`;
  const rest = friends.length - 1;
  return `${first} y ${rest} amigo${rest > 1 ? "s" : ""} más ${verb}`;
}

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

export function EventCard({ event, index = 0, onSetStatus, pending }) {
  const going = event.friends_going || [];
  const interested = event.friends_interested || [];
  const combined = [...going, ...interested].slice(0, 4);
  const goingText = friendsText(going, going.length === 1 ? "va a ir" : "van a ir");
  const interestedText = friendsText(interested, interested.length === 1 ? "tiene interés" : "tienen interés");
  const noFriends = going.length === 0 && interested.length === 0;

  const isVoy = event.my_status === "voy";
  const isInteresa = event.my_status === "me_interesa";

  const toggle = (status) => {
    onSetStatus(event.id, event.my_status === status ? "none" : status);
  };

  return (
    <motion.article
      data-testid={`event-card-${event.id}`}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.06, 0.4), ease: "easeOut" }}
      className="relative rounded-3xl overflow-hidden bg-[#121215] border border-white/10"
    >
      <div className="relative">
        <img
          src={mediaUrl(event.image_url)}
          alt={event.name}
          className="w-full h-[62vh] max-h-[460px] object-cover"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0C] via-[#0A0A0C]/70 to-transparent" />

        {event.genre && (
          <span
            className="absolute top-4 left-4 qv-glass text-white text-xs font-bold uppercase tracking-widest px-3 py-1.5 rounded-full border border-white/15"
            data-testid={`event-genre-${event.id}`}
          >
            {event.genre}
          </span>
        )}
        <span className="absolute top-4 right-4 qv-glass text-white text-xs font-bold px-3 py-1.5 rounded-full border border-white/15 flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" /> {formatDate(event.date)}
          {event.time ? ` · ${event.time}` : ""}
        </span>

        <div className="absolute bottom-0 w-full p-5 flex flex-col gap-4 z-10">
          {/* Social proof (core value) */}
          <div className="flex items-center gap-3 min-h-[42px]" data-testid={`event-social-${event.id}`}>
            {!noFriends ? (
              <>
                <div className="flex -space-x-3">
                  {combined.map((f, i) => (
                    <AvatarCircle key={f.user_id + i} name={f.name} picture={f.picture} size={38} />
                  ))}
                </div>
                <p className="text-sm text-white/90 leading-tight">
                  {goingText && (
                    <span className="block">
                      <span className="text-qv-primary">●</span>{" "}
                      <span className="font-semibold text-white">{goingText}</span>
                    </span>
                  )}
                  {interestedText && (
                    <span className="block text-white/70">
                      <span className="text-qv-secondary">●</span> {interestedText}
                    </span>
                  )}
                </p>
              </>
            ) : (
              <p className="text-sm text-white/45 italic" data-testid={`event-nofriends-${event.id}`}>
                Todavía ningún amigo se ha apuntado ✦ sé el primero
              </p>
            )}
          </div>

          <div>
            <h2 className="font-display text-2xl font-bold tracking-tight text-white leading-tight">
              {event.name}
            </h2>
            <p className="flex items-center gap-1.5 text-white/70 text-sm mt-1">
              <MapPin className="w-4 h-4 text-qv-secondary" /> {event.venue}
            </p>
          </div>

          {/* Status toggles */}
          <div className="grid grid-cols-2 gap-3">
            <button
              data-testid={`event-voy-btn-${event.id}`}
              disabled={pending}
              onClick={() => toggle("voy")}
              className={`h-12 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-300 active:scale-95 ${
                isVoy
                  ? "bg-qv-primary text-white shadow-[0_0_22px_rgba(255,0,85,0.45)]"
                  : "bg-white/5 border border-white/20 text-white/80"
              }`}
            >
              {isVoy && <Check className="w-4 h-4" />} Voy
            </button>
            <button
              data-testid={`event-interesa-btn-${event.id}`}
              disabled={pending}
              onClick={() => toggle("me_interesa")}
              className={`h-12 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-300 active:scale-95 ${
                isInteresa
                  ? "bg-qv-secondary text-black shadow-[0_0_22px_rgba(0,240,255,0.45)]"
                  : "bg-white/5 border border-white/20 text-white/80"
              }`}
            >
              {isInteresa && <Star className="w-4 h-4" />} Me interesa
            </button>
          </div>

          {/* Action button */}
          {event.has_commission && event.commission_url ? (
            <a
              data-testid={`event-ticket-btn-${event.id}`}
              href={event.commission_url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-12 rounded-2xl bg-white text-black font-bold text-sm flex items-center justify-center gap-2 transition-transform duration-300 hover:-translate-y-0.5 active:scale-95"
            >
              <Ticket className="w-4 h-4" /> Conseguir entrada
            </a>
          ) : event.more_info_url ? (
            <a
              data-testid={`event-info-btn-${event.id}`}
              href={event.more_info_url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-12 rounded-2xl bg-white/5 border border-white/20 text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-300 active:scale-95"
            >
              <ExternalLink className="w-4 h-4" /> Más información
            </a>
          ) : null}
        </div>
      </div>
    </motion.article>
  );
}
