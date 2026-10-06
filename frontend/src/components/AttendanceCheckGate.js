import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import api, { mediaThumb } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Moon, Check, X, Loader2, MapPin } from "lucide-react";
import { captureEvent } from "@/analytics/posthog";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

const DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

function nightLabel(dateIso) {
  if (!dateIso) return "";
  const d = new Date(`${dateIso}T12:00:00`);
  const today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 86400000);
  if (diff === 1) return i18n.t("attendance.night_last");
  if (diff === 2) return i18n.t("attendance.night_before");
  return i18n.t("attendance.night_on", { day: DAYS[d.getDay()] });
}

/**
 * Day-after attendance check. The app no longer assumes that marking "Voy"
 * means you went: the morning after, a semi-blocking sheet asks you to confirm.
 * Only confirmed parties become Nights (Recuerdos / Wrapped / insignias).
 */
export default function AttendanceCheckGate() {
  const { user, loading } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();
  const qc = useQueryClient();
  const [idx, setIdx] = useState(0);
  const [skipped, setSkipped] = useState(false);

  const { data } = useQuery({
    queryKey: ["attendance-pending"],
    queryFn: async () => (await api.get("/me/attendance-pending")).data,
    enabled: !!user && !loading,
    staleTime: 60_000,
    retry: false,
  });

  const items = useMemo(() => data?.items || [], [data]);
  const item = items[idx];

  const answer = useMutation({
    mutationFn: async ({ id, went }) => (await api.post(`/events/${id}/attendance`, { went })).data,
    onSuccess: (_r, vars) => {
      captureEvent("attendance_confirmed", { evento_id: vars.id, went: vars.went });
      qc.invalidateQueries({ queryKey: ["past-events"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["unread-count"] });
      if (idx + 1 >= items.length) {
        qc.invalidateQueries({ queryKey: ["attendance-pending"] });
        setIdx(0);
      } else {
        setIdx((i) => i + 1);
      }
    },
  });

  useEffect(() => {
    if (!user) return;
    setSkipped(sessionStorage.getItem("qv_attendance_skipped") === "1");
  }, [user]);

  const onLogin = location.pathname === "/login" || location.pathname.startsWith("/auth");
  const onMomento = location.pathname === "/momento";
  const onboarded = localStorage.getItem("qv_onboarded") === "1";

  if (!user || onLogin || onMomento || !onboarded || skipped || !item) return null;

  const skip = () => {
    sessionStorage.setItem("qv_attendance_skipped", "1");
    setSkipped(true);
  };

  const busy = answer.isPending;

  return (
    <AnimatePresence>
      <motion.div
        key="attendance-gate"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[92] flex items-end sm:items-center justify-center bg-black/85 backdrop-blur-md"
        data-testid="attendance-gate"
      >
        <motion.div
          initial={{ y: 60, opacity: 0, scale: 0.98 }}
          animate={{ y: 0, opacity: 1, scale: 1 }}
          transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="relative w-full sm:max-w-sm rounded-t-[32px] sm:rounded-[32px] border-t sm:border border-qv-secondary/35 bg-gradient-to-b from-[#14101c] via-[#0c0c10] to-black p-5 pb-7 overflow-hidden"
        >
          <div className="absolute -top-24 -right-16 w-56 h-56 rounded-full bg-qv-primary/20 blur-3xl pointer-events-none" />

          <button
            onClick={skip}
            data-testid="attendance-gate-skip"
            className="absolute top-3.5 right-3.5 w-9 h-9 rounded-full bg-white/8 border border-white/10 flex items-center justify-center active:scale-90"
            aria-label={t("attendance.later")}
          >
            <X className="w-4 h-4 text-white/60" />
          </button>

          <div className="relative flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-qv-secondary">
            <Moon className="w-3.5 h-3.5" /> {nightLabel(item.date)}
          </div>

          <h2 className="relative font-display text-[26px] leading-[1.05] font-black text-white mt-2">
            {t("attendance.title", { when: nightLabel(item.date) })}
          </h2>
          <p className="relative text-white/50 text-sm mt-1.5">
            {t("attendance.sub")}
          </p>

          <div className="relative mt-4 flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.05] p-3">
            <div className="w-16 h-16 rounded-xl overflow-hidden bg-white/5 shrink-0">
              {item.image_url ? (
                <img src={mediaThumb(item.image_url, 200)} alt={item.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-white/25">
                  <Moon className="w-6 h-6" />
                </div>
              )}
            </div>
            <div className="min-w-0">
              <p className="font-display font-black text-white text-[15px] leading-tight truncate">{item.name}</p>
              <p className="text-white/55 text-xs flex items-center gap-1 mt-1 truncate">
                <MapPin className="w-3 h-3 shrink-0" /> {item.venue}
              </p>
            </div>
          </div>

          <div className="relative mt-5 flex gap-2.5">
            <button
              data-testid="attendance-no"
              disabled={busy}
              onClick={() => answer.mutate({ id: item.id, went: false })}
              className="flex-1 h-14 rounded-2xl border border-white/12 bg-white/[0.05] text-white/75 font-bold text-sm active:scale-[0.98] disabled:opacity-50"
            >
              {t("attendance.no")}
            </button>
            <button
              data-testid="attendance-yes"
              disabled={busy}
              onClick={() => answer.mutate({ id: item.id, went: true })}
              className="flex-[1.4] h-14 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-white font-display font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60"
            >
              {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Check className="w-5 h-5" />}
              {t("attendance.yes")}
            </button>
          </div>

          {items.length > 1 && (
            <p className="relative text-center text-white/35 text-[11px] mt-3" data-testid="attendance-progress">
              {t("attendance.progress", { i: idx + 1, n: items.length })}
            </p>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
