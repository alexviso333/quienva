import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Flame, Users, Ticket, Lock, Clock, Star, Check } from "lucide-react";
import { AvatarCircle } from "@/components/AvatarCircle";
import { mediaUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const SALE_STATE_META = {
  no_a_la_venta: { label: "Próx.", cls: "bg-white/15 text-white/80", icon: Clock },
  a_la_venta: { label: "A la venta", cls: "bg-emerald-400/25 text-emerald-200", icon: Ticket },
  pocas_entradas: { label: "Pocas", cls: "bg-orange-400/30 text-orange-100", icon: Flame },
  agotado: { label: "Agotado", cls: "bg-white/10 text-white/50", icon: Lock },
};

function CompactPriceBadge({ event }) {
  const state = event.sale_state || "no_a_la_venta";
  const meta = SALE_STATE_META[state] || SALE_STATE_META.no_a_la_venta;
  const Icon = meta.icon;
  const price = event.current_price;
  const currency = event.currency || "EUR";
  const symbol = currency === "EUR" ? "€" : currency;
  if (!price && state === "no_a_la_venta") return null;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full backdrop-blur-sm ${meta.cls}`}
    >
      <Icon className="w-2.5 h-2.5" />
      {price ? `${Math.round(price)}${symbol}` : ""}
      {price && state !== "no_a_la_venta" ? " · " : ""}
      {meta.label}
    </span>
  );
}

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

/**
 * Compact tile used in horizontal carousels AND in "modo compacto" 2-column grid.
 * Not the full card — just a teaser. Tapping opens the event detail.
 */
export function CompactEventCard({ event, index = 0, width, onVoy }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const going = event.friends_going || [];
  const interested = event.friends_interested || [];
  const isVoy = event.my_status === "voy";
  const isInteresa = event.my_status === "me_interesa";
  const meEntry = user ? { user_id: "me", name: "Tú", picture: user.picture || "" } : null;
  const previewGoing = isVoy && meEntry ? [meEntry, ...going] : going;
  const previewInteresa = isInteresa && meEntry ? [meEntry, ...interested] : interested;
  const previewFriends = [...previewGoing, ...previewInteresa].slice(0, 3);
  const goingCount = going.length + (isVoy ? 1 : 0);
  const interestedCount = interested.length + (isInteresa ? 1 : 0);
  const friendCount = goingCount + interestedCount;

  const handleVoy = (e) => {
    e.stopPropagation();
    if (onVoy) onVoy(isVoy ? "none" : "voy");
  };

  return (
    <motion.div
      data-testid={`compact-card-${event.id}`}
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/event/${event.id}`)}
      onKeyDown={(e) => { if (e.key === "Enter") navigate(`/event/${event.id}`); }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.24), ease: "easeOut" }}
      className="relative rounded-2xl overflow-hidden bg-[#121215] border border-white/10 text-left flex-shrink-0 active:scale-[0.98] transition-transform cursor-pointer"
      style={width ? { width } : undefined}
    >
      <div className="relative aspect-[4/5]">
        {event.image_url ? (
          <img src={mediaUrl(event.image_url)} alt={event.name} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f]" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0c] via-[#0a0a0c]/50 to-transparent" />

        {event.genre && (
          <span className="absolute top-2 left-2 qv-glass text-white text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full border border-white/15">
            {event.genre}
          </span>
        )}

        {event.featured && (
          <span className="absolute top-2 left-2 mt-6 bg-gradient-to-r from-yellow-300 to-amber-400 text-black text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full flex items-center gap-0.5 shadow-[0_0_10px_rgba(253,224,71,0.5)]">
            <Star className="w-2.5 h-2.5" fill="currentColor" /> Top
          </span>
        )}

        {friendCount > 0 && (
          <span className="absolute top-2 right-2 bg-qv-primary/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
            <Flame className="w-2.5 h-2.5" />
            {friendCount}
          </span>
        )}

        {onVoy && (
          <button
            data-testid={`compact-voy-${event.id}`}
            onClick={handleVoy}
            className={`absolute bottom-2 right-2 z-20 inline-flex items-center gap-0.5 rounded-full px-2 py-1 text-[10px] font-black uppercase tracking-wide backdrop-blur-sm active:scale-90 transition-colors border ${
              isVoy
                ? "bg-qv-primary text-white border-qv-primary"
                : "bg-black/50 text-white/90 border-white/25"
            }`}
            aria-label={isVoy ? "Quitar voy" : "Marcar voy"}
          >
            {isVoy ? <><Check className="w-2.5 h-2.5" /> Voy</> : "Voy"}
          </button>
        )}

        <div className="absolute bottom-0 w-full p-2.5 z-10">
          <h3 className="font-display font-bold text-white text-sm leading-tight line-clamp-2">{event.name}</h3>
          <p className="text-white/60 text-[11px] mt-0.5 truncate">
            {event.venue} · {formatDate(event.date)}
          </p>
          <div className="mt-1">
            <CompactPriceBadge event={event} />
          </div>
          {previewFriends.length > 0 ? (
            <div className="flex items-center gap-1.5 mt-1.5">
              <div className="flex -space-x-1.5">
                {previewFriends.map((f, i) => (
                  <AvatarCircle key={f.user_id + i} name={f.name} picture={f.picture} size={18} />
                ))}
              </div>
              <span className="text-[10px] text-white/70 font-semibold truncate">
                {goingCount > 0
                  ? `${goingCount} va${goingCount > 1 ? "n" : ""}`
                  : `${interestedCount} interesad${interestedCount > 1 ? "os" : "o"}`}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1 mt-1.5 text-[10px] text-white/40">
              <Users className="w-3 h-3" /> Sé el primero
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
