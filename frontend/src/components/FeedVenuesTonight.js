import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
  const { data: venues = [] } = useQuery({
    queryKey: ["venues"],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 5 * 60_000,
  });

  const t = todayIdx();
  const open = venues.filter(
    (v) =>
      Array.isArray(v.open_days) &&
      v.open_days.includes(t) &&
      // Only the "extra" plans: no FourVenues ticketing OR explicitly free entry.
      (!v.scraper_slug || v.free_entry)
  );

  if (open.length === 0) return null;

  const openLink = (v) => {
    const url = v.buy_url || (v.instagram ? `https://instagram.com/${v.instagram}` : "");
    if (url) window.open(url, "_blank", "noopener");
    else navigate("/locales");
  };

  return (
    <div className="pt-2" data-testid="feed-venues-tonight">
      <div className="px-4 flex items-center gap-2 mb-2">
        <Sparkles className="w-4 h-4 text-qv-secondary" />
        <div className="flex-1 min-w-0">
          <h3 className="font-display font-black text-white text-lg leading-none">También esta noche</h3>
          <p className="text-white/50 text-xs">Pubs y sitios sin entrada anticipada · abiertos hoy ({WD[t]})</p>
        </div>
        <button onClick={() => navigate("/locales")} className="text-qv-secondary text-xs font-bold flex items-center gap-0.5 active:scale-95">
          Locales <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex gap-3 overflow-x-auto hide-scrollbar px-4 pb-1">
        {open.map((v) => (
          <button
            key={v.id}
            data-testid={`venue-tonight-${v.id}`}
            onClick={() => openLink(v)}
            className="shrink-0 w-40 text-left rounded-2xl border border-white/10 bg-[#121215] p-3 active:scale-[0.98]"
          >
            <div className="flex items-center gap-1.5 mb-1">
              {v.type === "pub" ? <Beer className="w-3.5 h-3.5 text-amber-300" /> : <Ticket className="w-3.5 h-3.5 text-qv-secondary" />}
              <span className={`text-[9px] font-black uppercase tracking-wide px-1.5 py-0.5 rounded-full ${v.free_entry ? "bg-emerald-400/20 text-emerald-200" : "bg-white/10 text-white/70"}`}>
                {v.free_entry ? "Gratis" : "Entradas"}
              </span>
            </div>
            <p className="font-display font-bold text-white text-sm leading-tight line-clamp-2">{v.name}</p>
            <p className="text-white/45 text-[11px] mt-0.5 flex items-center gap-1 truncate">
              <MapPin className="w-3 h-3 shrink-0" /> {v.zone || v.city}
            </p>
            <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-qv-secondary">
              {v.buy_url ? <>Entradas <ChevronRight className="w-3 h-3" /></> : v.instagram ? <><Instagram className="w-3 h-3" /> Ver</> : <>Info <ChevronRight className="w-3 h-3" /></>}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
