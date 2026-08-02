import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Flame, Calendar, ChevronRight, Trophy, Sparkles } from "lucide-react";

const _BADGE_HINT = {
  total_events: (r) => `Ve a ${r} fiesta${r === 1 ? "" : "s"} más`,
  day_streak: (r) => `Sal ${r} día${r === 1 ? "" : "s"} más seguidos`,
  week_streak: (r) => `${r} semana${r === 1 ? "" : "s"} más de fiesta`,
  friends_count: (r) => `Añade ${r} amigo${r === 1 ? "" : "s"} más`,
  tickets_count: (r) => `Compra ${r} entrada${r === 1 ? "" : "s"} más`,
  venues_count: (r) => `Ve a ${r} local${r === 1 ? "" : "es"} nuevo${r === 1 ? "" : "s"}`,
};

/**
 * Prominent streak + points banner on top of the Feed.
 * Shows current day streak, week streak, and next milestone.
 * Not just weekends — also weekday streaks are visible now.
 */
export function StreakBanner() {
  const navigate = useNavigate();
  const { data: streak } = useQuery({
    queryKey: ["streak-full"],
    queryFn: async () => (await api.get("/me/streak-full")).data,
    staleTime: 60_000,
  });
  const { data: badges } = useQuery({
    queryKey: ["me-points"],
    queryFn: async () => (await api.get("/me/badges")).data,
    staleTime: 60_000,
  });
  const { data: nextList = [] } = useQuery({
    queryKey: ["next-badges"],
    queryFn: async () => (await api.get("/me/next-badges?limit=1")).data,
    staleTime: 60_000,
  });
  const nextBadge = nextList[0];

  if (!streak) return null;

  const dayStreak = streak.day_streak || 0;
  const weekStreak = streak.week_streak || 0;
  const bestDay = streak.best_day_streak || 0;
  const bestWeek = streak.best_week_streak || 0;
  const nextDay = streak.next_day_milestone;
  const nextWeek = streak.next_week_milestone;
  const points = badges?.points?.total || 0;
  const isCold = dayStreak === 0 && weekStreak === 0;

  return (
    <button
      data-testid="streak-banner"
      onClick={() => navigate("/profile")}
      className="w-full text-left rounded-2xl overflow-hidden border border-white/10 bg-gradient-to-r from-[#1a0a12] via-[#0f0910] to-[#0a1a1f] active:scale-[0.99] transition-transform"
    >
      <div className="relative flex items-center gap-4 px-4 py-3">
        <div className="absolute inset-0 opacity-40 bg-[radial-gradient(ellipse_at_top_right,_rgba(255,0,85,0.30),transparent_65%)]" />
        {/* day streak */}
        <div className="relative flex items-center gap-1.5">
          <Flame className={`w-5 h-5 ${dayStreak > 0 ? "text-orange-400" : "text-white/40"}`} />
          <span className="font-display text-xl font-black text-white leading-none">{dayStreak}</span>
          <span className="text-[10px] uppercase tracking-wide text-white/50 font-bold">días</span>
        </div>
        <span className="relative w-px h-6 bg-white/10" />
        {/* week streak */}
        <div className="relative flex items-center gap-1.5">
          <Calendar className={`w-5 h-5 ${weekStreak > 0 ? "text-qv-secondary" : "text-white/40"}`} />
          <span className="font-display text-xl font-black text-white leading-none">{weekStreak}</span>
          <span className="text-[10px] uppercase tracking-wide text-white/50 font-bold">sem</span>
        </div>
        {/* points */}
        <div className="relative ml-auto flex items-center gap-1.5">
          <Trophy className="w-4 h-4 text-yellow-300" />
          <span className="font-display font-black text-yellow-300 text-lg leading-none">{points.toLocaleString("es-ES")}</span>
          <ChevronRight className="w-4 h-4 text-white/30" />
        </div>
      </div>

      {nextBadge && (
        <div className="relative flex items-center gap-2 px-4 pb-2.5 -mt-1" data-testid="next-badge-inline">
          <Sparkles className="w-3 h-3 text-qv-secondary shrink-0" />
          <span className="text-white/70 text-[11px] font-semibold shrink-0 truncate max-w-[45%]">{nextBadge.name}</span>
          <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full bg-gradient-to-r from-qv-primary to-qv-secondary" style={{ width: `${Math.min(100, nextBadge.progress)}%` }} />
          </div>
          <span className="text-yellow-300 text-[11px] font-bold shrink-0">+{nextBadge.points}</span>
        </div>
      )}

      {isCold && !nextBadge && (
        <p className="relative text-white/50 text-[11px] px-4 pb-2.5 -mt-1 italic">Marca &apos;Voy&apos; a un plan para empezar tu racha.</p>
      )}
    </button>
  );
}
