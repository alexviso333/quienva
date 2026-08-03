import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl, API } from "@/lib/api";
import { formatPartyDate } from "@/lib/format";
import { AvatarCircle } from "@/components/AvatarCircle";
import { EventAlbum } from "@/components/EventAlbum";
import { EventMoment } from "@/components/EventMoment";
import {
  ArrowLeft, MapPin, Clock, Ticket, ExternalLink, Send, Check, Star, Navigation, CheckCircle2, Loader2, Bell,
} from "lucide-react";
import { toast } from "sonner";

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
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: event, isLoading } = useQuery({
    queryKey: ["event", id],
    queryFn: async () => (await api.get(`/events/${id}`)).data,
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
      if (status === "voy") toast.success("¡Apuntado! 🎉");
      if (status === "estuve") toast.success("Guardado en tus recuerdos ✨");
    },
    onError: (_e, _s, ctx) => {
      if (ctx?.prev) qc.setQueryData(["event", id], ctx.prev);
      toast.error("No se pudo actualizar");
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
      toast.error("No se pudo guardar");
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
      toast.error("No se pudo actualizar el aviso");
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["event", id] }),
  });

  if (isLoading || !event) {
    return (
      <div className="min-h-screen qv-app-bg flex items-center justify-center">
        <Loader2 className="w-7 h-7 text-qv-primary animate-spin" />
      </div>
    );
  }

  const isPast = event.date < todayStr();
  const isVoy = event.my_status === "voy";
  const isInteresa = event.my_status === "me_interesa";
  const isEstuve = event.my_status === "estuve";
  const toggle = (s) => setStatus.mutate(event.my_status === s ? "none" : s);

  const mapQuery = encodeURIComponent(`${event.address || event.venue}, ${event.city || "Palma de Mallorca"}`);
  const shareWhatsApp = () => {
    const link = `${API}/share/event/${event.id}`;
    const text = `${event.name} — ¿vienes? 👀\n${link}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
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
            <img src={mediaUrl(event.image_url)} alt={event.name} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f]" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0C] via-[#0A0A0C]/50 to-transparent" />

          <button
            data-testid="detail-back"
            onClick={() => navigate(-1)}
            className="absolute top-6 left-4 w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <button
            data-testid="detail-follow"
            onClick={() => setFollow.mutate(!event.is_following)}
            className="absolute top-6 right-16 w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
            aria-label="Avisarme de cambios"
          >
            <Bell className={`w-5 h-5 ${event.is_following ? "text-qv-secondary" : "text-white"}`} fill={event.is_following ? "currentColor" : "none"} />
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
              {isEstuve ? <><CheckCircle2 className="w-5 h-5" /> Estuve aquí</> : "Estuve aquí"}
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
                {isVoy && <Check className="w-5 h-5" />} Voy
              </button>
              <button
                data-testid="detail-interesa-btn"
                onClick={() => toggle("me_interesa")}
                className={`h-12 rounded-2xl font-bold flex items-center justify-center gap-2 active:scale-95 transition-colors duration-300 ${
                  isInteresa ? "bg-qv-secondary text-black shadow-[0_0_20px_rgba(0,240,255,0.4)]" : "bg-white/5 border border-white/20 text-white/80"
                }`}
              >
                {isInteresa && <Star className="w-5 h-5" />} Me interesa
              </button>
            </div>
          )}

          {!isPast && (event.has_commission && event.commission_url ? (
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
                  ? "Ver disponibilidad"
                  : event.sale_state === "solo_lista"
                  ? "Apuntarme a la lista"
                  : "Conseguir entrada"}
                {price ? <span className="opacity-90">· desde {Math.round(price)}€</span> : null}
              </a>
              {saleBadge && (
                <p className={`text-center text-xs font-bold ${event.sale_state === "pocas_entradas" ? "text-yellow-300 animate-pulse" : "text-white/50"}`}>
                  {saleBadge}
                </p>
              )}
            </div>
          ) : event.more_info_url ? (
            <a
              data-testid="detail-info-btn"
              href={event.more_info_url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-12 rounded-2xl bg-white/5 border border-white/20 text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform"
            >
              <ExternalLink className="w-5 h-5" /> Más información
            </a>
          ) : null)}

          {/* "Ya tengo entrada" — social proof + conversion signal */}
          {!isPast && (
            <div className="flex items-center gap-3 rounded-2xl bg-white/[0.03] border border-white/10 p-3">
              <button
                data-testid="detail-ticket-owned-btn"
                onClick={() => setTicket.mutate(!event.my_has_ticket)}
                className={`shrink-0 h-10 px-4 rounded-xl font-bold text-sm flex items-center justify-center gap-1.5 active:scale-95 transition-colors ${
                  event.my_has_ticket ? "bg-qv-secondary text-black" : "bg-white/10 text-white/80 border border-white/20"
                }`}
              >
                {event.my_has_ticket ? <><CheckCircle2 className="w-4 h-4" /> Tengo entrada</> : <>🎟️ Ya tengo entrada</>}
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
                        ? `${ticketFriends.length} amigo${ticketFriends.length > 1 ? "s" : ""} ya ${ticketFriends.length > 1 ? "tienen" : "tiene"} entrada`
                        : `${totalTickets} ${totalTickets > 1 ? "personas tienen" : "persona tiene"} entrada`}
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-white/40 leading-tight">Sé el primero de tu grupo en pillar entrada 🎟️</p>
                )}
              </div>
            </div>
          )}

          {/* Friends */}
          <div className="flex flex-col gap-4">
            {isPast ? (
              <FriendRow title="Coincidiste con" color="#FF0055" friends={event.friends_attended} />
            ) : (
              <>
                <FriendRow title="Van a ir" color="#FF0055" friends={event.friends_going} />
                <FriendRow title="Les interesa" color="#00F0FF" friends={event.friends_interested} />
              </>
            )}
            {((isPast && (event.friends_attended || []).length === 0) ||
              (!isPast && (event.friends_going || []).length === 0 && (event.friends_interested || []).length === 0)) && (
              <p className="text-white/40 text-sm italic" data-testid="detail-nofriends">
                Todavía ningún amigo se ha apuntado.
              </p>
            )}
          </div>

          {/* Shared album — elevated so friends' photos don't get stuck in
              everyone's phone. Comes right after the friends block. */}
          <EventAlbum eventId={event.id} hasInterest={hasInterest} prominent />

          {/* El Momento — only during event window; component handles empty states */}
          {!isPast && <EventMoment eventId={event.id} hasInterest={hasInterest} />}

          {/* Map + directions */}
          <div>
            <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2">Cómo llegar</p>
            <div className="rounded-2xl overflow-hidden border border-white/10 h-48 bg-white/5">
              <iframe
                title="Mapa"
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
              <Navigation className="w-4 h-4 text-qv-secondary" /> Cómo llegar
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
