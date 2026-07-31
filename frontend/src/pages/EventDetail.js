import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { AddStoryButton } from "@/components/Stories";
import {
  ArrowLeft, MapPin, Clock, Ticket, ExternalLink, Send, Check, Star, Navigation, CheckCircle2, Loader2,
} from "lucide-react";
import { toast } from "sonner";

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  } catch {
    return dateStr;
  }
}
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
    onSuccess: (_d, status) => {
      qc.invalidateQueries({ queryKey: ["event", id] });
      qc.invalidateQueries({ queryKey: ["events"] });
      if (status === "voy") toast.success("¡Apuntado! 🎉");
      if (status === "estuve") toast.success("Guardado en tus recuerdos ✨");
    },
    onError: () => toast.error("No se pudo actualizar"),
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
    const link = `${window.location.origin}/event/${event.id}`;
    const text = `${event.name} · ${event.venue} · ${formatDate(event.date)} — ¿vienes? ${link}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
  };

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
            <span className="flex items-center gap-2 capitalize"><Clock className="w-4 h-4 text-qv-secondary" /> {formatDate(event.date)}{event.time ? ` · ${event.time}` : ""}</span>
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
            <a
              data-testid="detail-ticket-btn"
              href={event.commission_url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-12 rounded-2xl bg-white text-black font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform"
            >
              <Ticket className="w-5 h-5" /> Conseguir entrada
            </a>
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

          <AddStoryButton
            eventId={event.id}
            label="Subir historia de esta noche"
            className="h-12 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform"
          />
        </div>
      </div>
    </div>
  );
}
