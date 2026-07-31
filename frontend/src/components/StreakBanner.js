import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Flame, Calendar, ChevronRight, Trophy } from "lucide-react";

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
      className="w-full text-left rounded-2xl overflow-hidden border border-white/10 bg-gradient-to-br from-[#1a0a12] via-[#0f0910] to-[#0a1a1f] active:scale-[0.99] transition-transform"
    >
      <div className="relative p-4">
        <div className="absolute inset-0 opacity-40 bg-[radial-gradient(ellipse_at_top_right,_rgba(255,0,85,0.35),transparent_60%)]" />
        <div className="relative flex items-center gap-3">
          {/* Day streak pill */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${dayStreak > 0 ? "bg-orange-500/20" : "bg-white/5"}`}>
                <Flame className={`w-5 h-5 ${dayStreak > 0 ? "text-orange-400" : "text-white/40"}`} />
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-widest text-white/50 font-bold">Días seguidos</p>
                <p className="font-display text-2xl font-black text-white leading-none">
                  {dayStreak}
                  {bestDay > dayStreak && <span className="text-xs font-normal text-white/50 ml-1">/ máx {bestDay}</span>}
                </p>
              </div>
            </div>
            {nextDay && dayStreak > 0 && (
              <p className="text-[11px] text-orange-300/80 mt-2 pl-1">🔥 {nextDay - dayStreak} más para insignia</p>
            )}
          </div>

          <div className="h-14 w-px bg-white/10" />

          {/* Week streak pill */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${weekStreak > 0 ? "bg-qv-secondary/20" : "bg-white/5"}`}>
                <Calendar className={`w-5 h-5 ${weekStreak > 0 ? "text-qv-secondary" : "text-white/40"}`} />
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-widest text-white/50 font-bold">Semanas</p>
                <p className="font-display text-2xl font-black text-white leading-none">
                  {weekStreak}
                  {bestWeek > weekStreak && <span className="text-xs font-normal text-white/50 ml-1">/ máx {bestWeek}</span>}
                </p>
              </div>
            </div>
            {nextWeek && weekStreak > 0 && (
              <p className="text-[11px] text-qv-secondary/80 mt-2 pl-1">✨ {nextWeek - weekStreak} más para insignia</p>
            )}
          </div>

          <ChevronRight className="w-5 h-5 text-white/30 shrink-0" />
        </div>

        {/* Points row */}
        <div className="relative flex items-center justify-between mt-3 pt-3 border-t border-white/10">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-yellow-300" />
            <span className="font-display font-black text-yellow-300 text-lg">{points.toLocaleString("es-ES")}</span>
            <span className="text-white/60 text-xs uppercase tracking-widest font-bold">puntos</span>
          </div>
          <span
            onClick={(e) => { e.stopPropagation(); navigate("/top"); }}
            className="text-[11px] text-qv-secondary font-bold uppercase tracking-widest cursor-pointer active:opacity-70"
          >
            Ver ranking →
          </span>
        </div>

        {isCold && (
          <p className="relative text-white/50 text-[11px] mt-2 italic">Marca &apos;Voy&apos; a un plan para empezar tu racha.</p>
        )}
      </div>
    </button>
  );
}
