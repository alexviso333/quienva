import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Sparkles, ChevronRight } from "lucide-react";

const STAT_HINT = {
  total_events: (r) => `Ve a ${r} fiesta${r === 1 ? "" : "s"} más`,
  day_streak: (r) => `Sal ${r} día${r === 1 ? "" : "s"} más seguidos`,
  week_streak: (r) => `${r} semana${r === 1 ? "" : "s"} más de fiesta`,
  weekday_count: (r) => `${r} fiesta${r === 1 ? "" : "s"} más entre semana`,
  sunday_count: (r) => `${r} domingo${r === 1 ? "" : "s"} más de fiesta`,
  friends_count: (r) => `Añade ${r} amigo${r === 1 ? "" : "s"} más`,
  referrals_count: (r) => `Invita ${r} amigo${r === 1 ? "" : "s"} más`,
  tickets_count: (r) => `Compra ${r} entrada${r === 1 ? "" : "s"} más`,
  genres_count: (r) => `Prueba ${r} género${r === 1 ? "" : "s"} nuevo${r === 1 ? "" : "s"}`,
  venues_count: (r) => `Ve a ${r} local${r === 1 ? "" : "es"} nuevo${r === 1 ? "" : "s"}`,
  captures_count: (r) => `Sube ${r} momento${r === 1 ? "" : "s"} más`,
  stories_count: (r) => `Sube ${r} historia${r === 1 ? "" : "s"} más`,
  album_uploads: (r) => `Sube ${r} foto${r === 1 ? "" : "s"} más al álbum`,
};

/**
 * Small motivational banner on the Feed showing the closest next badge.
 * Users see "you're 1 event away from ..." with the badge preview.
 */
export function NextBadgeBanner() {
  const navigate = useNavigate();
  const { data: list = [] } = useQuery({
    queryKey: ["next-badges"],
    queryFn: async () => (await api.get("/me/next-badges?limit=1")).data,
    staleTime: 60_000,
  });
  const b = list[0];
  if (!b) return null;
  const hint = (STAT_HINT[b.stat_key] || ((r) => `${r} más para desbloquear`))(b.remaining);
  return (
    <button
      data-testid="next-badge-banner"
      onClick={() => navigate("/profile")}
      className="w-full text-left rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex items-center gap-3 active:scale-[0.99] transition-transform"
    >
      <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-300 flex items-center justify-center text-2xl shrink-0">
        {b.emoji}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] uppercase tracking-widest text-qv-secondary font-bold flex items-center gap-1">
          <Sparkles className="w-3 h-3" /> A punto de desbloquear
        </p>
        <p className="font-bold text-white truncate">{b.name} <span className="text-yellow-300 text-xs ml-1">+{b.points} pts</span></p>
        <div className="mt-1 h-1 rounded-full bg-white/10 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-qv-primary to-qv-secondary" style={{ width: `${Math.min(100, b.progress)}%` }} />
        </div>
        <p className="text-white/60 text-xs mt-1">{hint}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-white/30 shrink-0" />
    </button>
  );
}
