import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { Sparkles, ChevronRight } from "lucide-react";

const HINT_KEYS = new Set([
  "total_events", "day_streak", "week_streak", "weekday_count", "sunday_count",
  "friends_count", "referrals_count", "tickets_count", "genres_count",
  "venues_count", "captures_count", "stories_count", "album_uploads",
]);

/**
 * Small motivational banner on the Feed showing the closest next badge.
 * Users see "you're 1 event away from ..." with the badge preview.
 */
export function NextBadgeBanner() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: list = [] } = useQuery({
    queryKey: ["next-badges"],
    queryFn: async () => (await api.get("/me/next-badges?limit=1")).data,
    staleTime: 60_000,
  });
  const b = list[0];
  if (!b) return null;
  const hint = HINT_KEYS.has(b.stat_key)
    ? t(`badgehint.${b.stat_key}`, { count: b.remaining })
    : t("badgehint.fallback", { count: b.remaining });
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
          <Sparkles className="w-3 h-3" /> {t("nextbadge.about_to_unlock")}
        </p>
        <p className="font-bold text-white truncate">{b.name} <span className="text-yellow-300 text-xs ml-1">+{t("nextbadge.pts", { points: b.points })}</span></p>
        <div className="mt-1 h-1 rounded-full bg-white/10 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-qv-primary to-qv-secondary" style={{ width: `${Math.min(100, b.progress)}%` }} />
        </div>
        <p className="text-white/60 text-xs mt-1">{hint}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-white/30 shrink-0" />
    </button>
  );
}
