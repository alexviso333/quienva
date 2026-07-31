import { motion } from "framer-motion";
import { Ticket, ExternalLink, MapPin, Clock, Check, Star, Send, CheckCircle2 } from "lucide-react";
import { AvatarCircle } from "@/components/AvatarCircle";
import { mediaUrl } from "@/lib/api";

function friendsText(friends, verb) {
  if (!friends || friends.length === 0) return null;
  const first = friends[0].name.split(" ")[0];
  if (friends.length === 1) return `${first} ${verb}`;
  const rest = friends.length - 1;
  return `${first} y ${rest} ${verb}`;
}

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

const todayStr = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
};

export function EventCard({ event, index = 0, onSetStatus, pending, highlight, cardRef }) {
  const isPast = event.date < todayStr();
  const going = event.friends_going || [];
  const interested = event.friends_interested || [];
  const attended = event.friends_attended || [];

  const previewFriends = (isPast ? attended : [...going, ...interested]).slice(0, 4);

  const goingText = friendsText(going, going.length === 1 ? "va" : "van");
  const interestedText = friendsText(interested, interested.length === 1 ? "tiene interés" : "tienen interés");

  const isVoy = event.my_status === "voy";
  const isInteresa = event.my_status === "me_interesa";
  const isEstuve = event.my_status === "estuve";

  const toggle = (status) => onSetStatus(event.id, event.my_status === status ? "none" : status);

  const shareWhatsApp = () => {
    const link = `${window.location.origin}/feed?event=${event.id}`;
    const text = `${event.name} · ${event.venue} · ${formatDate(event.date)}${event.time ? " " + event.time : ""} — míralo en ¿Quién va? y dime si vienes 👀 ${link}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
  };

  return (
    <motion.article
      ref={cardRef}
      data-testid={`event-card-${event.id}`}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.05, 0.3), ease: "easeOut" }}
      className={`relative rounded-2xl overflow-hidden bg-[#121215] border transition-colors duration-500 ${
        highlight ? "border-qv-secondary shadow-[0_0_0_2px_rgba(0,240,255,0.5)]" : "border-white/10"
      }`}
    >
      {/* Image banner */}
      <div className="relative h-40">
        {event.image_url ? (
          <img src={mediaUrl(event.image_url)} alt={event.name} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f]" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-[#121215] via-[#121215]/40 to-transparent" />

        {event.genre && (
          <span
            data-testid={`event-genre-${event.id}`}
            className="absolute top-3 left-3 qv-glass text-white text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border border-white/15"
          >
            {event.genre}
          </span>
        )}

        <button
          data-testid={`event-share-btn-${event.id}`}
          onClick={shareWhatsApp}
          aria-label="Compartir por WhatsApp"
          className="absolute top-3 right-3 w-8 h-8 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
        >
          <Send className="w-4 h-4" />
        </button>

        <div className="absolute bottom-0 w-full p-3 z-10">
          <h2 className="font-display text-lg font-bold tracking-tight text-white leading-tight line-clamp-1">
            {event.name}
          </h2>
          <div className="flex items-center gap-2 text-white/70 text-xs mt-0.5">
            <span className="flex items-center gap-1 min-w-0">
              <MapPin className="w-3.5 h-3.5 text-qv-secondary shrink-0" />
              <span className="truncate">{event.venue}</span>
            </span>
            <span className="flex items-center gap-1 shrink-0">
              <Clock className="w-3.5 h-3.5" /> {formatDate(event.date)}{event.time ? ` · ${event.time}` : ""}
            </span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-3 flex flex-col gap-2.5">
        {/* Social proof — core value */}
        <div className="flex items-center gap-2.5 min-h-[34px]" data-testid={`event-social-${event.id}`}>
          {previewFriends.length > 0 ? (
            <>
              <div className="flex -space-x-2.5 shrink-0">
                {previewFriends.map((f, i) => (
                  <AvatarCircle key={f.user_id + i} name={f.name} picture={f.picture} size={30} />
                ))}
              </div>
              <p className="text-xs text-white/85 leading-tight">
                {isPast ? (
                  isEstuve && attended.length > 0 ? (
                    <span className="font-semibold text-white">Coincidiste con {friendsText(attended, attended.length === 1 ? "" : "más").trim()}</span>
                  ) : (
                    <span className="font-semibold text-white">{friendsText(attended, attended.length === 1 ? "estuvo" : "estuvieron")}</span>
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
              {isPast ? "¿Estuviste aquí? Márcalo abajo" : "Todavía ningún amigo se ha apuntado · sé el primero"}
            </p>
          )}
        </div>

        {/* Actions */}
        {isPast ? (
          <button
            data-testid={`event-estuve-btn-${event.id}`}
            disabled={pending}
            onClick={() => toggle("estuve")}
            className={`h-10 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-300 active:scale-95 ${
              isEstuve
                ? "bg-qv-primary text-white shadow-[0_0_18px_rgba(255,0,85,0.4)]"
                : "bg-white/5 border border-white/20 text-white/80"
            }`}
          >
            {isEstuve ? <><CheckCircle2 className="w-4 h-4" /> Estuve aquí</> : "Estuve aquí"}
          </button>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <button
                data-testid={`event-voy-btn-${event.id}`}
                disabled={pending}
                onClick={() => toggle("voy")}
                className={`h-10 rounded-xl font-bold text-sm flex items-center justify-center gap-1.5 transition-colors duration-300 active:scale-95 ${
                  isVoy ? "bg-qv-primary text-white shadow-[0_0_18px_rgba(255,0,85,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
                }`}
              >
                {isVoy && <Check className="w-4 h-4" />} Voy
              </button>
              <button
                data-testid={`event-interesa-btn-${event.id}`}
                disabled={pending}
                onClick={() => toggle("me_interesa")}
                className={`h-10 rounded-xl font-bold text-sm flex items-center justify-center gap-1.5 transition-colors duration-300 active:scale-95 ${
                  isInteresa ? "bg-qv-secondary text-black shadow-[0_0_18px_rgba(0,240,255,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
                }`}
              >
                {isInteresa && <Star className="w-4 h-4" />} Me interesa
              </button>
            </div>

            {event.has_commission && event.commission_url ? (
              <a
                data-testid={`event-ticket-btn-${event.id}`}
                href={event.commission_url}
                target="_blank"
                rel="noopener noreferrer"
                className="h-9 rounded-xl bg-white text-black font-bold text-sm flex items-center justify-center gap-2 transition-transform duration-300 hover:-translate-y-0.5 active:scale-95"
              >
                <Ticket className="w-4 h-4" /> Conseguir entrada
              </a>
            ) : event.more_info_url ? (
              <a
                data-testid={`event-info-btn-${event.id}`}
                href={event.more_info_url}
                target="_blank"
                rel="noopener noreferrer"
                className="h-9 rounded-xl bg-white/5 border border-white/20 text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors duration-300 active:scale-95"
              >
                <ExternalLink className="w-4 h-4" /> Más información
              </a>
            ) : null}
          </>
        )}
      </div>
    </motion.article>
  );
}
