import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { ReportFlag } from "@/components/ReportBlock";
import { Zap, Camera, Timer } from "lucide-react";

/**
 * "El Momento" — our own take on the BeReal-style capture during a party.
 * Admin triggers the prompt; users have 2 minutes to upload for on-time points.
 * After uploading, users can see their friends' captures side-by-side.
 */
export function EventMoment({ eventId, hasInterest, past = false }) {
  const navigate = useNavigate();
  const [secLeft, setSecLeft] = useState(null);

  const { data: status } = useQuery({
    queryKey: ["moment-status", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/moment/status`)).data,
    refetchInterval: 15000,
    retry: false,
  });

  const { data: gallery = [] } = useQuery({
    queryKey: ["moment-gallery", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/moment/gallery`)).data,
    enabled: !!status?.my_capture,
    refetchInterval: 15000,
    retry: false,
  });

  // Countdown to on_time_deadline
  useEffect(() => {
    if (!status?.prompt?.on_time_deadline || status?.my_capture) {
      setSecLeft(null);
      return;
    }
    const tick = () => {
      const deadline = new Date(status.prompt.on_time_deadline).getTime();
      const now = Date.now();
      const sec = Math.max(0, Math.round((deadline - now) / 1000));
      setSecLeft(sec);
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [status?.prompt?.on_time_deadline, status?.my_capture]);

  if (!hasInterest) return null;

  // Memories mode (past party): show ONLY the gallery of moments captured that
  // night, next to the shared album. No capture CTA. If I didn't capture, there's
  // nothing of mine to show, so render nothing.
  if (past && !status?.my_capture) return null;

  // No active prompt yet
  if (!status?.prompt) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-yellow-300/15 flex items-center justify-center">
            <Zap className="w-5 h-5 text-yellow-300" />
          </div>
          <div>
            <p className="font-bold text-white">El Momento</p>
            <p className="text-white/50 text-xs">Durante la fiesta te pediremos una foto sorpresa. Prepárate.</p>
          </div>
        </div>
      </div>
    );
  }

  // Already uploaded — show gallery
  if (status.my_capture) {
    return (
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-widest text-white/40 font-bold mb-2">
          <Zap className="w-4 h-4 text-yellow-300" /> El Momento
          {status.my_capture.on_time && (
            <span className="text-yellow-300 font-bold">• A tiempo • +30 pts</span>
          )}
        </p>
        <div className="grid grid-cols-3 gap-1.5" data-testid="moment-gallery">
          {gallery.map((c) => (
            <div key={c.id} className="aspect-square rounded-xl overflow-hidden bg-black relative">
              <img src={mediaThumb(c.image_url, 500)} alt="" className="w-full h-full object-cover" loading="lazy" />
              <div className="absolute bottom-1 left-1 flex items-center gap-1 bg-black/50 rounded-full px-1.5 py-0.5">
                <AvatarCircle name={c.author?.name || ""} picture={c.author?.picture || ""} size={16} ring={false} />
                <span className="text-white text-[10px] font-bold">{c.author?.name?.split(" ")[0]}</span>
              </div>
              {c.on_time && (
                <div className="absolute top-1 right-1 bg-yellow-300 text-black text-[9px] font-bold px-1.5 py-0.5 rounded-full">A TIEMPO</div>
              )}
              {!c.is_mine && (
                <div className="absolute top-1 left-1 w-6 h-6 rounded-full bg-black/50 flex items-center justify-center">
                  <ReportFlag targetType="moment" targetId={c.id} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Prompt active but not uploaded — show camera CTA + countdown
  const isOnTimeStill = secLeft !== null && secLeft > 0;
  return (
    <div className="rounded-2xl border-2 border-yellow-300/50 bg-gradient-to-br from-yellow-300/10 via-transparent to-transparent p-4 animate-pulse-slow" data-testid="moment-active">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-12 h-12 rounded-full bg-yellow-300/20 flex items-center justify-center">
          <Zap className="w-6 h-6 text-yellow-300" />
        </div>
        <div className="flex-1">
          <p className="font-display font-black text-white text-lg leading-none">¡El Momento!</p>
          <p className="text-yellow-200/80 text-xs">Haz una foto ahora mismo y gánate +30 puntos.</p>
        </div>
      </div>
      {isOnTimeStill ? (
        <div className="flex items-center gap-2 mb-3 justify-center">
          <Timer className="w-4 h-4 text-yellow-300" />
          <span className="font-display text-3xl font-black text-yellow-300 tabular-nums">
            {Math.floor(secLeft / 60)}:{String(secLeft % 60).padStart(2, "0")}
          </span>
        </div>
      ) : (
        <p className="text-center text-white/60 text-xs mb-3">Se acabó el tiempo bonus, pero aún puedes subirla.</p>
      )}
      <button
        data-testid="moment-capture-btn"
        onClick={() => navigate("/momento")}
        className="w-full h-12 rounded-2xl bg-yellow-300 text-black font-bold flex items-center justify-center gap-2 active:scale-95"
      >
        <Camera className="w-5 h-5" /> Hacer la foto
      </button>
    </div>
  );
}
