import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { PartyPopper, Users, Bell, ChevronRight, Sparkles, Loader2, ShieldCheck } from "lucide-react";
import { subscribeToPush } from "@/lib/push";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import GroupInviteStep from "@/components/GroupInviteStep";
import FindFriends from "@/components/FindFriends";

const SLIDES = [
  { icon: PartyPopper, color: "text-qv-primary", titleKey: "onboarding.slide1_title", bodyKey: "onboarding.slide1_body" },
  { icon: Users, color: "text-qv-secondary", titleKey: "onboarding.slide2_title", bodyKey: "onboarding.slide2_body" },
  { icon: Bell, color: "text-yellow-300", titleKey: "onboarding.slide3_title", bodyKey: "onboarding.slide3_body" },
];

export default function Onboarding() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [privacyStep, setPrivacyStep] = useState(false);
  const [notifStep, setNotifStep] = useState(false);
  const [inviteStep, setInviteStep] = useState(false);
  const [attendancePriv, setAttendancePriv] = useState("amigos");
  const [momentPriv, setMomentPriv] = useState("amigos");
  // First-run notification choices. new_event = "all my city" alerts (opt-in);
  // the rest are the useful per-event alerts. Saved to /me/notif-prefs.
  const [notifPrefs, setNotifPrefs] = useState({
    new_event: true,
    tickets_on_sale: true,
    tickets_price_down: true,
    friend_going: true,
  });
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
          toast.success(t("onboarding.toast_notif"));
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

  const saveNotifPrefs = async () => {
    try {
      await api.put("/me/notif-prefs", { prefs: notifPrefs });
    } catch (e) {
      /* non-fatal: defaults apply, user can change in Settings */
    }
  };

  const next = () => {
    if (i < SLIDES.length - 1) setI(i + 1);
    else if (!privacyStep) setPrivacyStep(true);
    else if (!notifStep) setNotifStep(true);
    else if (!inviteStep) { saveNotifPrefs(); setInviteStep(true); }
    else finish(true);
  };

  return (
    <div className="min-h-screen qv-app-bg flex flex-col px-6 py-10" data-testid="onboarding">
      <div className="flex justify-between items-center">
        <span className="text-qv-secondary text-xs font-bold uppercase tracking-widest">
          <Sparkles className="w-3.5 h-3.5 inline mr-1" /> {t("onboarding.welcome")}
        </span>
        <button onClick={() => finish(false)} className="text-white/50 text-sm">{t("onboarding.skip")}</button>
      </div>

      {inviteStep ? (
        <div className="flex-1 overflow-y-auto hide-scrollbar flex flex-col gap-6 py-6" data-testid="onboarding-invite">
          <div className="text-center flex flex-col items-center gap-3">
            <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
              <Users className="w-10 h-10 text-qv-primary" />
            </div>
            <h1 className="font-display text-3xl font-bold text-white">{t("groupinvite.title", "Monta tu grupo")}</h1>
            <p className="text-white/60 text-sm max-w-xs leading-relaxed">{t("groupinvite.subtitle", "Ponle nombre a tu grupo y trae a tu gente de un toque. Veréis a qué fiesta va cada uno.")}</p>
          </div>
          <GroupInviteStep />
          <div className="flex items-center gap-3 px-1">
            <span className="flex-1 h-px bg-white/10" />
            <span className="text-white/35 text-xs uppercase tracking-widest">{t("groupinvite.or_contacts", "o busca en tus contactos")}</span>
            <span className="flex-1 h-px bg-white/10" />
          </div>
          <div className="-mx-6">
            <FindFriends />
          </div>
        </div>
      ) : notifStep ? (
        <div className="flex-1 flex flex-col justify-center gap-6 py-6" data-testid="onboarding-notif">
          <div className="text-center flex flex-col items-center gap-3">
            <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
              <Bell className="w-10 h-10 text-yellow-300" />
            </div>
            <h1 className="font-display text-3xl font-bold text-white">{t("onboarding.notif_title", { defaultValue: "¿Qué avisos quieres?" })}</h1>
            <p className="text-white/60 text-sm max-w-xs leading-relaxed">
              {t("onboarding.notif_sub", { defaultValue: "Elige qué notificaciones recibir. Podrás cambiarlo cuando quieras en Ajustes." })}
            </p>
          </div>
          <div className="flex flex-col gap-2.5">
            {[
              ["new_event", t("onboarding.notif_city", { defaultValue: "Todas las fiestas de mi ciudad" }), t("onboarding.notif_city_d", { defaultValue: "Avísame de cualquier fiesta nueva cerca" })],
              ["tickets_on_sale", t("onboarding.notif_sale", { defaultValue: "Entradas a la venta" }), t("onboarding.notif_sale_d", { defaultValue: "Cuando salen a la venta" })],
              ["tickets_price_down", t("onboarding.notif_drop", { defaultValue: "Bajadas de precio" }), t("onboarding.notif_drop_d", { defaultValue: "Cuando baja el precio de una entrada" })],
              ["friend_going", t("onboarding.notif_friends", { defaultValue: "Amigos se apuntan" }), t("onboarding.notif_friends_d", { defaultValue: "Cuando un amigo se apunta a un plan" })],
            ].map(([key, label, desc]) => (
              <button
                key={key}
                data-testid={`onb-notif-${key}`}
                onClick={() => setNotifPrefs((p) => ({ ...p, [key]: !p[key] }))}
                className={`flex items-center gap-3 rounded-2xl border p-3.5 text-left active:scale-[0.99] transition-colors ${notifPrefs[key] ? "bg-qv-primary/15 border-qv-primary" : "bg-white/5 border-white/12"}`}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-semibold">{label}</p>
                  <p className="text-white/45 text-xs">{desc}</p>
                </div>
                <span className={`w-11 h-6 rounded-full flex-shrink-0 relative transition-colors ${notifPrefs[key] ? "bg-qv-primary" : "bg-white/15"}`}>
                  <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${notifPrefs[key] ? "left-[22px]" : "left-0.5"}`} />
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : privacyStep ? (
        <div className="flex-1 flex flex-col justify-center gap-7 py-6" data-testid="onboarding-privacy">
          <div className="text-center flex flex-col items-center gap-3">
            <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
              <ShieldCheck className="w-10 h-10 text-qv-secondary" />
            </div>
            <h1 className="font-display text-3xl font-bold text-white">{t("onboarding.privacy_title")}</h1>
            <p className="text-white/60 text-sm max-w-xs leading-relaxed">
              {t("onboarding.privacy_sub")}
            </p>
          </div>

          <div>
            <p className="text-sm font-bold text-white mb-2">
              {t("onboarding.q_attendance")} <span className="text-white/50 font-medium">{t("onboarding.q_attendance_hint")}</span>
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[["todos", t("onboarding.opt_all")], ["amigos", t("onboarding.opt_friends_only")], ["nadie", t("onboarding.opt_none")]].map(([val, label]) => (
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
            <p className="text-sm font-bold text-white mb-2">{t("onboarding.q_moment")}</p>
            <div className="grid grid-cols-2 gap-2">
              {[["amigos", t("onboarding.opt_friends_only")], ["publico", t("onboarding.opt_moment_public")]].map(([val, label]) => (
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
                <h1 className="font-display text-3xl font-bold text-white">{t(SLIDES[i].titleKey)}</h1>
                <p className="text-white/60 text-base max-w-xs leading-relaxed">{t(SLIDES[i].bodyKey)}</p>
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
        {inviteStep ? t("onboarding.start") : t("onboarding.next")}
        {!inviteStep && <ChevronRight className="w-5 h-5" />}
      </button>
    </div>
  );
}
