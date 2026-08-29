import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Zap, Camera, Users } from "lucide-react";

/**
 * BIG "El Momento" banner for the feed. When a moment is active during a party,
 * this shows a large, impossible-to-miss card at the very top of the feed so the
 * user sees it the second they open the app and feels the urge to capture NOW.
 *
 * Reuses the ["active-moment"] query (same key as MomentGate) so react-query
 * dedupes the request — no extra network cost.
 */
export default function MomentFeedBanner() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const { data: moment } = useQuery({
    queryKey: ["active-moment"],
    queryFn: async () => (await api.get("/me/active-moment")).data,
    enabled: !!user && !loading,
    refetchInterval: 30000,
    staleTime: 10000,
    retry: false,
  });

  if (!user || !moment?.active) return null;

  return (
    <div className="px-4 pt-1 pb-3" data-testid="moment-feed-banner">
      <button
        onClick={() => navigate("/momento")}
        className="relative w-full overflow-hidden rounded-3xl border-2 border-yellow-300/60 bg-gradient-to-br from-[#241d05] via-[#141207] to-black p-5 text-left active:scale-[0.99] transition-transform shadow-[0_0_40px_-8px_rgba(253,224,71,0.45)]"
      >
        {/* glow pulse */}
        <span className="pointer-events-none absolute -top-10 -right-10 w-40 h-40 rounded-full bg-yellow-300/20 blur-2xl animate-pulse" />
        <div className="relative flex items-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-yellow-300/20 flex items-center justify-center shrink-0 animate-pulse">
            <Zap className="w-8 h-8 text-yellow-300" />
          </div>
          <div className="min-w-0">
            <p className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] font-black text-yellow-300">
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-300 animate-ping" />
              {t("momentgate.pill")}
            </p>
            <h2 className="font-display text-2xl font-black text-white leading-none mt-1">
              {t("momentgate.title")}
            </h2>
            {moment.event_name && (
              <p className="text-yellow-200/90 text-sm font-semibold truncate mt-0.5">{moment.event_name}</p>
            )}
          </div>
        </div>

        {moment.friends_captured > 0 && (
          <div className="relative mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
            <Users className="w-3.5 h-3.5 text-qv-secondary" />
            <span className="text-white/80 text-xs font-semibold">
              {t("momentgate.friends_captured", { count: moment.friends_captured })}
            </span>
          </div>
        )}

        <div className="relative mt-4 w-full h-12 rounded-2xl bg-gradient-to-r from-yellow-300 to-amber-400 text-black font-display font-black text-sm flex items-center justify-center gap-2">
          <Camera className="w-5 h-5" /> {t("momentgate.go")}
        </div>
      </button>
    </div>
  );
}
