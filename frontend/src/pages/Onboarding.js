import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { PartyPopper, Users, Bell, ChevronRight, Sparkles, Loader2, ShieldCheck } from "lucide-react";
import { subscribeToPush } from "@/lib/push";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";

const SLIDES = [
  {
    icon: PartyPopper,
    color: "text-qv-primary",
    title: "Descubre los planes",
    body: "Las mejores fiestas de Palma, con precio, hora, local y entrada directa. Marca 'Voy' o 'Me interesa' con un toque.",
  },
  {
    icon: Users,
    color: "text-qv-secondary",
    title: "Con tus amigos",
    body: "Ve quién va a cada fiesta, y si sois 3+ del grupo, haceos la foto de grupo. Cuando estéis dentro, salta El Momento: foto sorpresa delante y detrás.",
  },
  {
    icon: Bell,
    color: "text-yellow-300",
    title: "No te pierdas nada",
    body: "Te avisamos cuando un amigo se apunta, cuando salen últimas entradas o cuando salta El Momento. Actívalas para vivirlo al máximo.",
  },
];

export default function Onboarding() {
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [privacyStep, setPrivacyStep] = useState(false);
  const [attendancePriv, setAttendancePriv] = useState("amigos");
  const [momentPriv, setMomentPriv] = useState("amigos");
  const Icon = SLIDES[i].icon;

  useEffect(() => {
    // If already onboarded, skip
    if (localStorage.getItem("qv_onboarded") === "1") {
      nav("/feed", { replace: true });
    }
  }, [nav]);

  const finish = async (activate) => {
    setBusy(true);
    try {
      // Persist the privacy choices the user made in the final step. (If they
      // skipped before reaching it, the server defaults — "amigos" — already apply.)
      if (privacyStep) {
        try {
          await api.put("/auth/profile", { attendance_privacy: attendancePriv, moment_privacy: momentPriv });
        } catch (e) { /* ignore, defaults stay */ }
      }
      if (activate) {
        try {
          await subscribeToPush();
          toast.success("¡Notificaciones activadas! ⚡");
        } catch (e) { /* browser denied — continue anyway */ }
        if (user) localStorage.setItem(`qv_push_granted_${user.user_id}`, "1");
      }
      try { await refreshUser(); } catch (e) { /* ignore */ }
    } finally {
      setBusy(false);
    }
    localStorage.setItem("qv_onboarded", "1");
    nav("/feed", { replace: true });
  };

  const next = () => {
    if (i < SLIDES.length - 1) setI(i + 1);
    else if (!privacyStep) setPrivacyStep(true);
    else finish(true);
  };

  return (
    <div className="min-h-screen qv-app-bg flex flex-col px-6 py-10" data-testid="onboarding">
      <div className="flex justify-between items-center">
        <span className="text-qv-secondary text-xs font-bold uppercase tracking-widest">
          <Sparkles className="w-3.5 h-3.5 inline mr-1" /> Bienvenido
        </span>
        <button onClick={() => finish(false)} className="text-white/50 text-sm">Saltar</button>
      </div>

      {privacyStep ? (
        <div className="flex-1 flex flex-col justify-center gap-7 py-6" data-testid="onboarding-privacy">
          <div className="text-center flex flex-col items-center gap-3">
            <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
              <ShieldCheck className="w-10 h-10 text-qv-secondary" />
            </div>
            <h1 className="font-display text-3xl font-bold text-white">Tu privacidad</h1>
            <p className="text-white/60 text-sm max-w-xs leading-relaxed">
              Decide quién ve tu actividad. Podrás cambiarlo cuando quieras en Ajustes.
            </p>
          </div>

          <div>
            <p className="text-sm font-bold text-white mb-2">
              ¿Quién puede ver a qué fiestas vas? <span className="text-white/50 font-medium">(tu {'"Voy"'})</span>
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[["todos", "Todos"], ["amigos", "Solo amigos"], ["nadie", "Nadie"]].map(([val, label]) => (
                <button
                  key={val}
                  data-testid={`onb-att-${val}`}
                  onClick={() => setAttendancePriv(val)}
                  className={`h-12 rounded-2xl border text-sm font-bold active:scale-95 transition-colors ${
                    attendancePriv === val ? "bg-qv-primary/15 border-qv-primary text-white" : "bg-white/5 border-white/12 text-white/65"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-sm font-bold text-white mb-2">¿Quién puede ver tu Momento?</p>
            <div className="grid grid-cols-2 gap-2">
              {[["amigos", "Solo amigos"], ["publico", "Todos (público)"]].map(([val, label]) => (
                <button
                  key={val}
                  data-testid={`onb-mom-${val}`}
                  onClick={() => setMomentPriv(val)}
                  className={`h-12 rounded-2xl border text-sm font-bold active:scale-95 transition-colors ${
                    momentPriv === val ? "bg-qv-secondary/15 border-qv-secondary text-white" : "bg-white/5 border-white/12 text-white/65"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <AnimatePresence mode="wait">
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.35 }}
                className="flex flex-col items-center gap-6"
              >
                <div className="w-24 h-24 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
                  <Icon className={`w-11 h-11 ${SLIDES[i].color}`} />
                </div>
                <h1 className="font-display text-3xl font-bold text-white">{SLIDES[i].title}</h1>
                <p className="text-white/60 text-base max-w-xs leading-relaxed">{SLIDES[i].body}</p>
              </motion.div>
            </AnimatePresence>
          </div>

          <div className="flex justify-center gap-2 mb-8">
            {SLIDES.map((_, idx) => (
              <span
                key={idx}
                className={`h-1.5 rounded-full transition-all ${idx === i ? "w-8 bg-qv-primary" : "w-1.5 bg-white/20"}`}
              />
            ))}
          </div>
        </>
      )}

      <button
        data-testid="onboarding-next"
        onClick={next}
        disabled={busy}
        className="h-14 rounded-2xl bg-qv-primary text-white font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60"
      >
        {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : null}
        {privacyStep ? "Activar notificaciones y empezar" : "Siguiente"}
        {!privacyStep && <ChevronRight className="w-5 h-5" />}
      </button>
    </div>
  );
}
