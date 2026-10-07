import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { PartyPopper, MapPin, ChevronRight, Loader2, Sparkles, Check } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "@/lib/notify";
import { useTranslation } from "react-i18next";

/**
 * SPRINT 4 — Onboarding reducido de 6 pasos a 2:
 *   Paso 1: Elegir ciudad.
 *   Paso 2: "¡Mira qué hay esta noche en [ciudad]!" -> va a Tonight (/feed).
 *
 * El resto (privacidad, notificaciones, grupo, contactos) se movió a prompts
 * contextuales dentro de la app. Los defaults del servidor (attendance_privacy
 * y moment_privacy = "amigos") ya aplican sin preguntar nada aquí, para que un
 * usuario que llega desde WhatsApp vea una fiesta real en menos de 30s.
 */
export default function Onboarding() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { user, setUser, refreshUser } = useAuth();
  const [step, setStep] = useState(0); // 0 = ciudad, 1 = "esta noche"
  const [busy, setBusy] = useState(false);
  const [cities, setCities] = useState([]);
  const [selected, setSelected] = useState(user?.city || null);

  useEffect(() => {
    if (localStorage.getItem("qv_onboarded") === "1") {
      nav("/feed", { replace: true });
    }
  }, [nav]);

  useEffect(() => {
    api.get("/cities").then(({ data }) => {
      if (data?.cities?.length) setCities(data.cities);
    }).catch(() => {});
  }, []);

  const cityLabel = (() => {
    const c = cities.find((x) => x.id === selected);
    return (c?.label || selected || "").split(",")[0];
  })();

  const pickCity = async (cityId) => {
    setSelected(cityId);
    try {
      const { data } = await api.put("/auth/profile", { city: cityId });
      setUser(data);
      try { localStorage.setItem("qv_user", JSON.stringify(data)); } catch { /* ignore */ }
    } catch (e) { /* non-fatal: will retry on finish */ }
  };

  const goTonight = async () => {
    setBusy(true);
    try {
      if (selected && selected !== user?.city) {
        try {
          const { data } = await api.put("/auth/profile", { city: selected });
          setUser(data);
        } catch (e) { /* ignore */ }
      }
      try { await refreshUser(); } catch (e) { /* ignore */ }
    } finally {
      setBusy(false);
    }
    try { localStorage.setItem("qv_onboarded", "1"); } catch { /* ignore */ }
    nav("/feed", { replace: true });
  };

  const skip = () => {
    try { localStorage.setItem("qv_onboarded", "1"); } catch { /* ignore */ }
    nav("/feed", { replace: true });
  };

  return (
    <div className="min-h-screen qv-app-bg flex flex-col px-6 py-10" data-testid="onboarding">
      <div className="flex justify-between items-center">
        <span className="text-qv-secondary text-xs font-bold uppercase tracking-widest">
          <Sparkles className="w-3.5 h-3.5 inline mr-1" /> {t("onboarding.welcome")}
        </span>
        <button onClick={skip} data-testid="onboarding-skip" className="text-white/50 text-sm">{t("onboarding.skip")}</button>
      </div>

      <AnimatePresence mode="wait">
        {step === 0 ? (
          <motion.div
            key="city"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.3 }}
            className="flex-1 flex flex-col justify-center gap-7 py-6"
            data-testid="onboarding-city"
          >
            <div className="text-center flex flex-col items-center gap-3">
              <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
                <MapPin className="w-10 h-10 text-qv-secondary" />
              </div>
              <h1 className="font-display text-3xl font-black text-white">
                {t("onboarding.city_title", "¿En qué ciudad sales?")}
              </h1>
              <p className="text-white/60 text-sm max-w-xs leading-relaxed">
                {t("onboarding.city_sub", "Te enseñamos las fiestas de tu ciudad. Podrás cambiarla cuando quieras.")}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {cities.map((c) => {
                const on = selected === c.id;
                const short = (c.label || c.id).split(",")[0];
                return (
                  <button
                    key={c.id}
                    data-testid={`onb-city-${c.id}`}
                    onClick={() => pickCity(c.id)}
                    className={`h-14 rounded-2xl border text-sm font-bold flex items-center justify-center gap-2 active:scale-95 transition-colors ${
                      on
                        ? "bg-qv-secondary/15 border-qv-secondary text-white"
                        : "bg-white/5 border-white/12 text-white/70"
                    }`}
                  >
                    {c.emoji ? <span>{c.emoji}</span> : null}
                    {short}
                    {on && <Check className="w-4 h-4 text-qv-secondary" />}
                  </button>
                );
              })}
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="tonight"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.3 }}
            className="flex-1 flex flex-col items-center justify-center text-center gap-6"
            data-testid="onboarding-tonight"
          >
            <div className="w-24 h-24 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
              <PartyPopper className="w-11 h-11 text-qv-primary" />
            </div>
            <h1 className="font-display text-4xl font-black text-white leading-tight">
              {t("onboarding.tonight_title", "¡Mira qué hay esta noche")}<br />
              <span className="text-qv-primary">{cityLabel ? `en ${cityLabel}!` : "!"}</span>
            </h1>
            <p className="text-white/60 text-base max-w-xs leading-relaxed">
              {t("onboarding.tonight_sub", "Descubre las fiestas de hoy y marca a cuáles vas. Así de fácil.")}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {step === 0 ? (
        <button
          data-testid="onboarding-next"
          onClick={() => setStep(1)}
          disabled={!selected}
          className="h-14 rounded-2xl bg-qv-primary text-white font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-40"
        >
          {t("onboarding.next")}
          <ChevronRight className="w-5 h-5" />
        </button>
      ) : (
        <button
          data-testid="onboarding-finish"
          onClick={goTonight}
          disabled={busy}
          className="h-14 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-black text-base flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60"
        >
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : null}
          {t("onboarding.tonight_cta", "Ver las fiestas")}
          <ChevronRight className="w-5 h-5" />
        </button>
      )}
    </div>
  );
}
