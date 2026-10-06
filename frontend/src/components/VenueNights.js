import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Sparkles, Camera, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import api, { mediaThumb } from "@/lib/api";

const fmtNight = (d) => {
  try {
    return new Date(`${d}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
  } catch {
    return d;
  }
};

// Past nights at the same venue: proof the place is alive + a door into the
// memories (album / El Momento) of each night.
export function VenueNights({ eventId, venue }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["venue-nights", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/venue-nights`)).data,
    enabled: !!eventId,
    staleTime: 300000,
  });

  const nights = data?.nights || [];
  if (!nights.length) return null;

  return (
    <div data-testid="venue-nights">
      <h3 className="text-sm font-black uppercase tracking-wider text-white/70 mb-3 flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-qv-secondary" />
        {t("event.venue_nights_title", "Noches en {{venue}}", { venue: venue || data?.venue || "" })}
      </h3>
      <div className="flex gap-3 overflow-x-auto -mx-5 px-5 pb-1 hide-scrollbar">
        {nights.map((n) => (
          <button
            key={n.id}
            type="button"
            data-testid={`venue-night-${n.id}`}
            onClick={() => navigate(`/event/${n.id}`)}
            className="shrink-0 w-[132px] text-left active:scale-[0.97] transition-transform"
          >
            <div className="relative w-full h-[168px] rounded-2xl overflow-hidden border border-white/12 bg-white/[0.05]">
              {n.image_url ? (
                <img
                  src={mediaThumb(n.image_url, 400)}
                  alt={n.name}
                  loading="lazy"
                  className="w-full h-full object-cover opacity-80"
                />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] to-[#0a1a1f]" />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />
              <div className="absolute bottom-0 p-2.5">
                <p className="text-[11px] font-bold text-white/60 capitalize">{fmtNight(n.date)}</p>
                <p className="text-[12px] font-bold text-white leading-tight line-clamp-2">{n.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-2.5 mt-1.5 text-[11px] text-white/55">
              {n.attended > 0 && (
                <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {n.attended}</span>
              )}
              {n.photos > 0 && (
                <span className="flex items-center gap-1"><Camera className="w-3 h-3" /> {n.photos}</span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
