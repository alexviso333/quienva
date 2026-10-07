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
        className="relative w-full overflow-hidden rounded-3xl border border-white/20 bg-gradient-to-br from-[#2a0916] via-[#0f0820] to-black p-5 text-left active:scale-[0.99] transition-transform shadow-[0_20px_55px_-10px_rgba(236,72,153,0.55)]"
      >
        {/* 3 glows en contratiempo */}
        <span className="pointer-events-none absolute -top-14 -left-10 w-56 h-56 rounded-full bg-pink-500/35 blur-3xl animate-pulse" />
        <span className="pointer-events-none absolute -bottom-16 -right-10 w-64 h-64 rounded-full bg-cyan-400/25 blur-[90px] animate-pulse" style={{ animationDelay: "500ms" }} />
        <span className="pointer-events-none absolute top-1/2 left-1/3 w-32 h-32 rounded-full bg-yellow-300/25 blur-2xl animate-pulse" style={{ animationDelay: "900ms" }} />

        <div className="relative flex items-center gap-3">
          <div className="relative w-16 h-16 shrink-0">
            <span className="absolute inset-0 rounded-2xl bg-yellow-300/40 blur-md animate-ping" />
            <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-yellow-300 via-orange-400 to-pink-500 flex items-center justify-center shadow-lg shadow-pink-500/40">
              <Zap className="w-9 h-9 text-black" strokeWidth={2.5} />
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <p className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] font-black text-pink-300">
              <span className="w-1.5 h-1.5 rounded-full bg-pink-400 animate-ping" />
              EN VIVO · {t("momentgate.pill", "Hacer tu Momento")}
            </p>
            <h2
              className="font-display text-2xl font-black leading-none mt-1 bg-gradient-to-r from-yellow-300 via-pink-400 to-cyan-300 bg-clip-text text-transparent"
              style={{ letterSpacing: "-0.02em" }}
            >
              {t("momentgate.title_wow", "¡EL MOMENTO!")}
            </h2>
            {moment.event_name && (
              <p className="text-white/85 text-xs font-semibold truncate mt-1">📍 {moment.event_name}</p>
            )}
          </div>
        </div>

        {moment.friends_captured > 0 && (
          <div className="relative mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 border border-white/15">
            <Users className="w-3.5 h-3.5 text-cyan-300" />
            <span className="text-white/90 text-xs font-semibold">
              {t("momentgate.friends_captured", { count: moment.friends_captured })}
            </span>
          </div>
        )}

        <div className="relative mt-4 w-full h-12 rounded-2xl bg-gradient-to-r from-pink-500 via-orange-400 to-yellow-300 text-black font-display font-black text-sm flex items-center justify-center gap-2 shadow-[0_10px_28px_-8px_rgba(236,72,153,0.6)]">
          <Camera className="w-5 h-5" strokeWidth={2.5} /> {t("momentgate.go_wow", "¡HACER MI MOMENTO AHORA!")}
        </div>
      </button>
    </div>
  );
}
