import React, { createContext, useCallback, useContext, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import { startGoogleLogin } from "@/lib/googleAuth";
import { Sparkles, X } from "lucide-react";

const GuestGateContext = createContext({ requireAuth: () => true });

export function useGuestGate() {
  return useContext(GuestGateContext);
}

/**
 * Intent-based registration gate.
 *
 * Guests (no session) can freely browse read-only content. The moment they try
 * to do something social (Voy / Me interesa, amigos, chats, perfil, avisos…)
 * we call `requireAuth(reason)` which pops a friendly modal instead of firing a
 * doomed authenticated request. Authenticated users are never interrupted.
 */
export function GuestGateProvider({ children }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [reason, setReason] = useState(null);

  const requireAuth = useCallback(
    (actionReason) => {
      if (user) return true;
      setReason(actionReason || t("guestgate.default_reason"));
      return false;
    },
    [user]
  );

  const close = () => setReason(null);
  const go = (path) => {
    setReason(null);
    navigate(path);
  };

  return (
    <GuestGateContext.Provider value={{ requireAuth }}>
      {children}
      {reason !== null && (
        <div
          className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm"
          data-testid="guest-gate"
          onClick={close}
        >
          <div
            className="w-full max-w-md m-0 sm:m-4 rounded-t-3xl sm:rounded-3xl border border-white/10 bg-[#121215] p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] relative overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(255,0,85,0.18),transparent_60%)] pointer-events-none" />
            <button
              onClick={close}
              className="absolute top-4 right-4 text-white/50 active:scale-90"
              data-testid="guest-gate-close"
              aria-label={t("guestgate.close")}
            >
              <X className="w-5 h-5" />
            </button>
            <div className="relative">
              <div className="w-12 h-12 rounded-2xl bg-qv-primary/20 flex items-center justify-center mb-4">
                <Sparkles className="w-6 h-6 text-qv-primary" />
              </div>
              <h2 className="font-display text-2xl font-black tracking-tight text-white">
                {t("guestgate.title")}<span className="text-qv-primary">.</span>
              </h2>
              <p className="text-white/60 text-sm mt-2 leading-snug">
                {t("guestgate.body_pre", { reason })}<span className="text-white font-semibold">{t("guestgate.body_bold")}</span>{t("guestgate.body_end")}
              </p>
              <button
                onClick={() => startGoogleLogin()}
                data-testid="guest-gate-google"
                className="mt-5 w-full h-12 rounded-2xl bg-white text-black font-bold text-sm flex items-center justify-center gap-3 active:scale-95 transition-transform"
              >
                <svg className="w-5 h-5" viewBox="0 0 48 48">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
                {t("guestgate.google")}
              </button>
              <div className="flex items-center gap-3 my-3">
                <div className="flex-1 h-px bg-white/10" />
                <span className="text-white/35 text-[10px] uppercase tracking-widest">{t("guestgate.or")}</span>
                <div className="flex-1 h-px bg-white/10" />
              </div>
              <button
                onClick={() => go("/login?mode=register")}
                data-testid="guest-gate-register"
                className="w-full h-12 rounded-2xl bg-qv-primary text-white font-bold active:scale-95 transition-transform"
              >
                {t("guestgate.register")}
              </button>
              <button
                onClick={() => go("/login")}
                data-testid="guest-gate-login"
                className="mt-2 w-full h-11 rounded-2xl bg-white/5 border border-white/15 text-white/80 font-semibold active:scale-95 transition-transform"
              >
                {t("guestgate.have_account")}
              </button>
            </div>
          </div>
        </div>
      )}
    </GuestGateContext.Provider>
  );
}
