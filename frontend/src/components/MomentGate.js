import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Zap, Camera, Users, X } from "lucide-react";

/**
 * Global "El Momento" gate.
 * - When there's a pending moment for the user, shows a BLOCKING full-screen
 *   modal as soon as the app opens (BeReal-style: do it now).
 * - "Ahora no" dismisses it for this session and, on the home feed, leaves a
 *   small unobtrusive pill at the top so it's always one tap away.
 */
export default function MomentGate() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [dismissed, setDismissed] = useState(false);

  const { data: moment } = useQuery({
    queryKey: ["active-moment"],
    queryFn: async () => (await api.get("/me/active-moment")).data,
    enabled: !!user && !loading,
    refetchInterval: 30000,
    staleTime: 10000,
    retry: false,
  });

  const promptId = moment?.prompt?.id;

  // Reset dismissal when a NEW moment arrives.
  useEffect(() => {
    if (!promptId) return;
    setDismissed(sessionStorage.getItem(`qv_moment_dismissed_${promptId}`) === "1");
  }, [promptId]);

  // Never show over the capture screen itself.
  const onMomentoPage = location.pathname === "/momento";
  const onLogin = location.pathname === "/login" || location.pathname.startsWith("/auth");

  // Don't stack modals: wait until the push-permission step has been resolved.
  const pushResolved = user ? localStorage.getItem(`qv_push_granted_${user.user_id}`) === "1" : false;

  // Only *block* during real party hours (20:00–06:00 local). Otherwise the
  // small pill is enough — no full-screen interruption in the middle of the day.
  const hourNow = new Date().getHours();
  const isNightWindow = hourNow >= 20 || hourNow < 6;

  if (!user || !moment?.active || onMomentoPage || onLogin || !pushResolved) return null;

  const go = () => navigate("/momento");
  const dismiss = () => {
    if (promptId) sessionStorage.setItem(`qv_moment_dismissed_${promptId}`, "1");
    setDismissed(true);
  };

  // Small pill (never overlaps the header — sits above the bottom nav) when
  // dismissed OR when it's outside the night window.
  if (dismissed || !isNightWindow) {
    if (location.pathname !== "/feed") return null;
    return (
      <button
        onClick={go}
        data-testid="moment-pill"
        className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-2 px-4 py-2 rounded-full bg-yellow-300 text-black font-display font-black text-xs shadow-lg shadow-yellow-300/30 active:scale-95 animate-pulse-slow"
      >
        <Zap className="w-4 h-4" /> Hacer tu Momento
      </button>
    );
  }

  // Blocking modal
  return (
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center p-6 bg-black/90 backdrop-blur-md"
      data-testid="moment-gate"
    >
      <div className="relative w-full max-w-sm rounded-3xl border-2 border-yellow-300/50 bg-gradient-to-br from-[#1a1608] via-[#0d0d0d] to-black p-6 text-center">
        <button
          onClick={dismiss}
          className="absolute top-3 right-3 w-9 h-9 rounded-full bg-white/10 flex items-center justify-center active:scale-90"
          data-testid="moment-gate-dismiss"
        >
          <X className="w-4 h-4 text-white/70" />
        </button>
        <div className="mx-auto w-16 h-16 rounded-full bg-yellow-300/20 flex items-center justify-center mb-4 animate-pulse">
          <Zap className="w-8 h-8 text-yellow-300" />
        </div>
        <h2 className="font-display text-2xl font-black text-white leading-tight">¡Es EL MOMENTO!</h2>
        <p className="text-yellow-200/90 text-sm mt-1 font-semibold truncate">{moment.event_name}</p>
        <p className="text-white/60 text-sm mt-3 leading-relaxed">
          Haz tu foto sorpresa (delante y detrás){" "}
          {moment.on_time ? <span className="text-yellow-300 font-bold">ahora para llevarte +30 puntos.</span> : "antes de que acabe la noche."}
        </p>
        {moment.friends_captured > 0 && (
          <div className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
            <Users className="w-3.5 h-3.5 text-qv-secondary" />
            <span className="text-white/80 text-xs font-semibold">
              {moment.friends_captured} amig{moment.friends_captured === 1 ? "o" : "os"} ya han subido la suya · verás las suyas cuando subas la tuya
            </span>
          </div>
        )}
        <button
          onClick={go}
          className="mt-5 w-full py-3.5 rounded-2xl bg-gradient-to-r from-yellow-300 to-amber-400 text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98]"
          data-testid="moment-gate-go"
        >
          <Camera className="w-5 h-5" /> Hacer mi Momento
        </button>
        <button
          onClick={dismiss}
          className="mt-2 w-full py-2.5 rounded-2xl text-white/50 text-xs font-semibold hover:text-white/80"
          data-testid="moment-gate-later"
        >
          Ahora no
        </button>
      </div>
    </div>
  );
}
