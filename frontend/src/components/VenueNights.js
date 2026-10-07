import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { CalendarDays, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import api, { mediaThumb } from "@/lib/api";

const fmtNight = (d) => {
  try {
    return new Date(`${d}T12:00:00`).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
  } catch {
    return d;
  }
};

/**
 * "Próximas noches en [discoteca]" — la agenda REAL del local, sin salir de la
 * ficha de la fiesta.
 *
 * Antes esto mostraba noches PASADAS del sitio, que no servían de nada y encima
 * se leían como "fiestas a las que fuiste" (y no era verdad). Ahora solo datos
 * comprobables: fecha, nombre y precio desde.
 */
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
      <h3 className="text-sm font-black uppercase tracking-wider text-white/70 mb-0.5 flex items-center gap-2">
        <CalendarDays className="w-4 h-4 text-qv-secondary" />
        {t("event.venue_nights_title", "Próximas noches en {{venue}}", { venue: venue || data?.venue || "" })}
      </h3>
      <p className="text-white/35 text-[11px] mb-3">{t("event.venue_nights_sub", "La agenda de este sitio")}</p>
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
                  className="w-full h-full object-cover opacity-90"
                />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] to-[#0a1a1f]" />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />
              <div className="absolute bottom-0 p-2.5">
                <p className="text-[11px] font-bold text-qv-secondary capitalize">{fmtNight(n.date)}</p>
                <p className="text-[12px] font-bold text-white leading-tight line-clamp-2">{n.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-2.5 mt-1.5 text-[11px] text-white/55">
              {n.time ? (
                <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {n.time}</span>
              ) : null}
              {n.price ? <span className="font-bold text-white/70">desde {Math.round(n.price)}€</span> : null}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
