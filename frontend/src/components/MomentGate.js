import { useEffect, useState, useMemo } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Zap, Camera, Users, X, Timer } from "lucide-react";
import { startMomentActivity, updateMomentActivity, endMomentActivity } from "@/lib/momentLiveActivity";

/**
 * Global "El Momento" gate — rediseñado "WOW".
 *
 * - Durante horario de fiesta (20:00–06:00) sale un modal full-screen BeReal-style
 *   con glow neón, countdown y aviso de "friends ya han subido la suya".
 * - El vibrato haptic (en móvil) se dispara al abrir el modal.
 * - Fuera del horario de fiesta solo deja la píldora al pie, no interrumpe.
 */
export default function MomentGate() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  // --- Admin preview mode: ?preview_moment=1 ----------------------------
  // Renders the WOW UI with mock data so the admin can see exactly how it
  // looks without having to wait for an actual Moment to fire. Only works
  // when the current user is admin.
  const previewOn = user?.role === "admin" && new URLSearchParams(location.search).get("preview_moment") === "1";
  const previewData = useMemo(() => {
    if (!previewOn) return null;
    const inSec = (s) => new Date(Date.now() + s * 1000).toISOString();
    return {
      active: true,
      event_id: "preview",
      event_name: "Fiesta de Prueba (Preview)",
      venue: "QuienVa HQ",
      on_time: true,
      friends_captured: 3,
      capturing_now: 12,
      prompt: {
        id: "preview-prompt",
        on_time_deadline: inSec(180), // 3-min countdown
        expires_at: inSec(60 * 60),
      },
    };
  }, [previewOn]);

  const { data: realMoment } = useQuery({
    queryKey: ["active-moment"],
    queryFn: async () => (await api.get("/me/active-moment")).data,
    enabled: !!user && !loading && !previewOn,
    refetchInterval: 30000,
    staleTime: 10000,
    retry: false,
  });

  const moment = previewOn ? previewData : realMoment;
  const promptId = moment?.prompt?.id;
  const deadline = moment?.prompt?.on_time_deadline;

  // --- iOS Dynamic Island / Live Activity nativa -----------------------
  // Si el Momento esta activo, arranca una Live Activity local en el
  // iPhone (noop en web/android). Cuando desaparece, la termina.
  const activeEventId = moment?.active && !previewOn ? moment.event_id : null;
  useEffect(() => {
    if (!activeEventId) return;
    startMomentActivity(moment);
    return () => { endMomentActivity(activeEventId); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeEventId]);
  // Actualiza contadores "subiendo ahora" cuando cambian.
  useEffect(() => {
    if (!activeEventId) return;
    updateMomentActivity(moment);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeEventId, moment?.capturing_now, moment?.friends_captured]);

  // Reset dismissal when a NEW moment arrives.
  useEffect(() => {
    if (!promptId) return;
    setDismissed(sessionStorage.getItem(`qv_moment_dismissed_${promptId}`) === "1");
  }, [promptId]);

  // Haptic burst + ticker only while the modal is actually visible.
  useEffect(() => {
    if (!promptId || dismissed) return;
    try { if (navigator?.vibrate) navigator.vibrate([30, 50, 30, 50, 80]); } catch (e) { /* ignore */ }
    const h = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(h);
  }, [promptId, dismissed]);

  // Never show over the capture screen itself.
  const onMomentoPage = location.pathname === "/momento";
  const onLogin = location.pathname === "/login" || location.pathname.startsWith("/auth");

  // Don't stack modals: wait until the push-permission step has been resolved.
  // Preview mode bypasses this gate so admins can inspect the UI anytime.
  const pushResolved = previewOn
    ? true
    : (user ? localStorage.getItem(`qv_push_granted_${user.user_id}`) === "1" : false);

  // Only *block* during real party hours (20:00–06:00 local). Otherwise the
  // small pill is enough — no full-screen interruption in the middle of the day.
  // Preview mode forces the night-window behaviour so the WOW modal always renders.
  const hourNow = new Date().getHours();
  const isNightWindow = previewOn ? true : (hourNow >= 20 || hourNow < 6);

  // Countdown in seconds remaining of the on_time window (+30 points reward).
  const secondsLeft = useMemo(() => {
    if (!deadline) return null;
    try {
      const d = new Date(deadline).getTime();
      return Math.max(0, Math.floor((d - now) / 1000));
    } catch (e) { return null; }
  }, [deadline, now]);
  const mm = secondsLeft != null ? String(Math.floor(secondsLeft / 60)).padStart(2, "0") : "--";
  const ss = secondsLeft != null ? String(secondsLeft % 60).padStart(2, "0") : "--";
  const onTime = secondsLeft != null && secondsLeft > 0;

  if (!user || !moment?.active || onMomentoPage || onLogin || !pushResolved) return null;

  const stripPreviewParam = () => {
    const sp = new URLSearchParams(location.search);
    sp.delete("preview_moment");
    const qs = sp.toString();
    navigate(location.pathname + (qs ? `?${qs}` : ""), { replace: true });
  };

  const go = () => {
    if (previewOn) {
      stripPreviewParam();
      return;
    }
    navigate("/momento");
  };
  const dismiss = () => {
    if (previewOn) {
      stripPreviewParam();
      setDismissed(true);
      return;
    }
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
        className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-yellow-300 via-orange-400 to-pink-500 text-black font-display font-black text-xs shadow-lg shadow-orange-500/40 active:scale-95 animate-pulse-slow"
      >
        <Zap className="w-4 h-4" /> {t("momentgate.pill")}
      </button>
    );
  }

  // Blocking WOW modal
  return (
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center p-5 bg-black/95 backdrop-blur-md"
      data-testid="moment-gate"
    >
      {/* Fondo con 2 glows radiales que laten en contratiempo. */}
      <span className="pointer-events-none absolute -top-20 -left-20 w-96 h-96 rounded-full bg-pink-500/35 blur-[90px] animate-pulse" />
      <span className="pointer-events-none absolute -bottom-24 -right-24 w-[28rem] h-[28rem] rounded-full bg-cyan-400/25 blur-[100px] animate-pulse" style={{ animationDelay: "500ms" }} />
      <span className="pointer-events-none absolute top-1/3 right-1/4 w-40 h-40 rounded-full bg-yellow-300/25 blur-3xl animate-pulse" style={{ animationDelay: "900ms" }} />

      <div className="relative w-full max-w-sm rounded-[32px] border border-white/15 bg-gradient-to-br from-[#1a0a22] via-[#0a0612] to-black p-6 text-center shadow-[0_30px_90px_-20px_rgba(236,72,153,0.6)]">
        {/* Borde iridiscente animado */}
        <span className="pointer-events-none absolute inset-0 rounded-[32px] p-[1.5px] bg-[conic-gradient(from_0deg,theme(colors.pink.500),theme(colors.cyan.400),theme(colors.yellow.300),theme(colors.pink.500))] animate-spin-slow opacity-70 -z-10" />

        <button
          onClick={dismiss}
          className="absolute top-3 right-3 w-9 h-9 rounded-full bg-white/10 flex items-center justify-center active:scale-90 z-10"
          data-testid="moment-gate-dismiss"
          aria-label="cerrar"
        >
          <X className="w-4 h-4 text-white/70" />
        </button>

        {/* Icono rayo con triple halo */}
        <div className="relative mx-auto w-20 h-20 mb-3">
          <span className="absolute inset-0 rounded-full bg-yellow-300/40 blur-xl animate-ping" />
          <span className="absolute inset-2 rounded-full bg-pink-500/40 blur-md animate-pulse" />
          <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-yellow-300 via-orange-400 to-pink-500 flex items-center justify-center shadow-lg shadow-pink-500/50">
            <Zap className="w-10 h-10 text-black" strokeWidth={2.5} />
          </div>
        </div>

        {/* Mini banner "LIVE" */}
        <p className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.3em] font-black text-pink-400 bg-pink-500/10 border border-pink-500/30 rounded-full px-3 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-pink-500 animate-ping" />
          EN VIVO · ES EL MOMENTO
        </p>

        {/* Título gigante en degradado */}
        <h2
          className="font-display text-[42px] font-black leading-none mt-3 bg-gradient-to-r from-yellow-300 via-pink-400 to-cyan-300 bg-clip-text text-transparent"
          style={{ letterSpacing: "-0.03em" }}
        >
          {t("momentgate.title_wow", "¡EL MOMENTO!")}
        </h2>
        <p className="text-white/85 text-sm mt-2 font-bold truncate">
          📍 {moment.event_name}
        </p>

        {/* Countdown chip */}
        {onTime && (
          <div
            data-testid="moment-countdown"
            className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-black border border-yellow-300/60 shadow-[0_0_30px_-5px_rgba(253,224,71,0.5)]"
          >
            <Timer className="w-4 h-4 text-yellow-300 animate-pulse" />
            <span className="font-mono text-xl font-black text-yellow-300 tabular-nums">{mm}:{ss}</span>
            <span className="text-[10px] text-yellow-200/70 uppercase tracking-wider font-bold">+30 pts</span>
          </div>
        )}
        {!onTime && (
          <p className="mt-3 text-white/60 text-xs leading-relaxed">
            {t("momentgate.desc_late", "antes de que acabe la noche.")}
          </p>
        )}

        {/* Social proof */}
        {moment.friends_captured > 0 ? (
          <div className="mt-4 inline-flex items-center gap-2 px-3.5 py-2 rounded-full bg-white/5 border border-white/15">
            <Users className="w-3.5 h-3.5 text-cyan-300" />
            <span className="text-white/90 text-xs font-semibold">
              {t("momentgate.friends_captured", { count: moment.friends_captured })}
            </span>
          </div>
        ) : (
          <p className="mt-4 text-white/50 text-[11px] leading-snug px-2">
            {t("momentgate.be_first", "Sé el primero de tu grupo esta noche 👀")}
          </p>
        )}

        {/* CTA ENORME */}
        <button
          onClick={go}
          className="relative mt-5 w-full py-4 rounded-2xl bg-gradient-to-r from-pink-500 via-orange-400 to-yellow-300 text-black font-display font-black text-base flex items-center justify-center gap-2 active:scale-[0.98] shadow-[0_15px_40px_-10px_rgba(236,72,153,0.6)] overflow-hidden"
          data-testid="moment-gate-go"
        >
          <span className="absolute inset-0 bg-white/20 translate-x-[-120%] group-hover:translate-x-[120%] transition-transform duration-700" />
          <Camera className="w-5 h-5" strokeWidth={2.5} /> {t("momentgate.go_wow", "¡HACER MI MOMENTO AHORA!")}
        </button>
        <button
          onClick={dismiss}
          className="mt-2 w-full py-2.5 rounded-2xl text-white/40 text-xs font-semibold hover:text-white/70 active:scale-95"
          data-testid="moment-gate-later"
        >
          {t("momentgate.later", "Ahora no")}
        </button>
      </div>
    </div>
  );
}
