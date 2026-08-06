import React, { createContext, useCallback, useContext, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
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
  const [reason, setReason] = useState(null);

  const requireAuth = useCallback(
    (actionReason) => {
      if (user) return true;
      setReason(actionReason || "seguir");
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
              aria-label="Cerrar"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="relative">
              <div className="w-12 h-12 rounded-2xl bg-qv-primary/20 flex items-center justify-center mb-4">
                <Sparkles className="w-6 h-6 text-qv-primary" />
              </div>
              <h2 className="font-display text-2xl font-black tracking-tight text-white">
                Crea tu cuenta<span className="text-qv-primary">.</span>
              </h2>
              <p className="text-white/60 text-sm mt-2 leading-snug">
                Regístrate gratis para {reason} y ver <span className="text-white font-semibold">quién de tus amigos</span> va a cada plan.
              </p>
              <button
                onClick={() => go("/login?mode=register")}
                data-testid="guest-gate-register"
                className="mt-5 w-full h-12 rounded-2xl bg-qv-primary text-white font-bold active:scale-95 transition-transform"
              >
                Crear cuenta gratis
              </button>
              <button
                onClick={() => go("/login")}
                data-testid="guest-gate-login"
                className="mt-2 w-full h-11 rounded-2xl bg-white/5 border border-white/15 text-white/80 font-semibold active:scale-95 transition-transform"
              >
                Ya tengo cuenta
              </button>
            </div>
          </div>
        </div>
      )}
    </GuestGateContext.Provider>
  );
}
