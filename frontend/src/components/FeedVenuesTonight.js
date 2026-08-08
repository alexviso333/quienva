import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { Beer, Ticket, MapPin, Instagram, ChevronRight, Sparkles } from "lucide-react";

const WD = ["L", "M", "X", "J", "V", "S", "D"];

function todayIdx() {
  // open_days convention: 0=Mon .. 6=Sun. JS getDay(): 0=Sun..6=Sat.
  return (new Date().getDay() + 6) % 7;
}

/**
 * "También esta noche" — recurring venues (pubs + free/non-ticketed clubs) that
 * are open TODAY. Kept SEPARATE from the FourVenues ticketed feed (that's the
 * commission business) but clearly VISIBLE so people who want free / non-club
 * plans find them without digging into Locales.
 */
export default function FeedVenuesTonight() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: venues = [] } = useQuery({
    queryKey: ["venues"],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 5 * 60_000,
  });

  const todayI = todayIdx();
  const open = venues.filter(
    (v) =>
      Array.isArray(v.open_days) &&
      v.open_days.includes(todayI) &&
      // Only the "extra" plans: no FourVenues ticketing OR explicitly free entry.
      (!v.scraper_slug || v.free_entry) &&
      // Beach clubs live in their own category (map / Locales), not here.
      v.type !== "beach_club"
  );

  if (open.length === 0) return null;

  const openLink = (v) => {
    const url = v.buy_url || (v.instagram ? `https://instagram.com/${v.instagram}` : "");
    if (url) window.open(url, "_blank", "noopener");
    else navigate("/locales");
  };

  return (
    <div className="pt-1" data-testid="feed-venues-tonight">
      <div className="px-4 flex items-center gap-2 mb-1.5">
        <div className="flex-1 min-w-0">
          <h3 className="text-white/70 text-xs font-bold uppercase tracking-widest">{t("venuestonight.title")}</h3>
          <p className="text-white/35 text-[11px]">{t("venuestonight.subtitle")}</p>
        </div>
        <button onClick={() => navigate("/locales")} className="text-white/40 text-[11px] font-bold flex items-center gap-0.5 active:scale-95">
          {t("venuestonight.locales")} <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex gap-2 overflow-x-auto hide-scrollbar px-4 pb-1">
        {open.map((v) => (
          <button
            key={v.id}
            data-testid={`venue-tonight-${v.id}`}
            onClick={() => openLink(v)}
            className="shrink-0 w-32 text-left rounded-xl border border-white/8 bg-white/[0.03] p-2.5 active:scale-[0.98]"
          >
            <div className="flex items-center gap-1 mb-0.5">
              {v.type === "pub" ? <Beer className="w-3 h-3 text-white/40" /> : <Ticket className="w-3 h-3 text-white/40" />}
              {v.free_entry && <span className="text-[8px] font-bold uppercase tracking-wide text-emerald-300/80">{t("venuestonight.free")}</span>}
            </div>
            <p className="font-semibold text-white/90 text-xs leading-tight line-clamp-2">{v.name}</p>
            <p className="text-white/35 text-[10px] mt-0.5 flex items-center gap-0.5 truncate">
              <MapPin className="w-2.5 h-2.5 shrink-0" /> {v.zone || v.city}
            </p>
            {v.open_time && (
              <p className="text-white/30 text-[10px] mt-0.5">🕒 {v.open_time}{v.close_time ? `–${v.close_time}` : ""}</p>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
