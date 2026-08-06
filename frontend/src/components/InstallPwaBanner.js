import { useEffect, useState, useCallback } from "react";
import { Download, X, Share, Plus } from "lucide-react";

const DISMISS_KEY = "qv_pwa_dismissed_at_v2";
const SNOOZE_DAYS = 4; // re-show the install reminder after this many days

// Detects the platform so we can show the right "add to home screen" flow.
function detectPlatform() {
  if (typeof navigator === "undefined") return "other";
  const ua = navigator.userAgent || "";
  const isIOS = /iphone|ipad|ipod/i.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (isIOS) return "ios";
  if (/android/i.test(ua)) return "android";
  return "other";
}

function isStandalone() {
  return (
    (typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(display-mode: standalone)").matches) ||
    (typeof navigator !== "undefined" && navigator.standalone === true)
  );
}

/**
 * Dismissable banner that teaches users to install the app to their home screen
 * so it behaves like a native app. On Android/Chrome it uses the native install
 * prompt; on iOS it shows the manual "Compartir → Añadir a pantalla de inicio"
 * steps (iOS has no programmatic install).
 */
export default function InstallPwaBanner() {
  const [platform] = useState(detectPlatform);
  const [deferred, setDeferred] = useState(null);
  const [visible, setVisible] = useState(false);
  const [showIosSteps, setShowIosSteps] = useState(false);

  useEffect(() => {
    if (isStandalone()) return; // already installed
    // Snooze: only stay hidden for SNOOZE_DAYS after the last dismissal, then
    // gently remind again (unless the app is already installed).
    const dismissedAt = Number(localStorage.getItem(DISMISS_KEY) || 0);
    if (dismissedAt && Date.now() - dismissedAt < SNOOZE_DAYS * 24 * 3600 * 1000) return;

    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferred(e);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // Mobile visitors who haven't installed should ALWAYS see the prompt, even
    // if the browser never fires beforeinstallprompt (iOS Safari never does, and
    // on Android the event can be missed). Desktop only shows via the native
    // event to avoid nagging people who can't really "install" from a laptop.
    if (platform === "ios" || platform === "android") setVisible(true);

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, [platform]);

  const dismiss = useCallback(() => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setVisible(false);
    setShowIosSteps(false);
  }, []);

  const install = useCallback(async () => {
    if (platform === "ios") {
      setShowIosSteps((s) => !s);
      return;
    }
    if (deferred) {
      deferred.prompt();
      try {
        await deferred.userChoice;
      } catch {
        /* ignore */
      }
      setDeferred(null);
      dismiss();
      return;
    }
    // Android (or other) without a captured native prompt → show manual steps.
    setShowIosSteps((s) => !s);
  }, [deferred, platform, dismiss]);

  if (!visible) return null;

  return (
    <div
      data-testid="pwa-install-banner"
      className="mx-4 mb-3 rounded-2xl border border-qv-primary/40 bg-gradient-to-br from-qv-primary/15 to-qv-secondary/10 p-3.5"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-qv-primary/20 flex items-center justify-center shrink-0">
          <Download className="w-5 h-5 text-qv-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-white font-bold text-sm leading-tight">Instala ¿Quién va? en tu móvil</p>
          <p className="text-white/60 text-xs mt-0.5 leading-snug">
            Añádela a tu pantalla de inicio y ábrela como una app: más rápida, a pantalla completa y con avisos.
          </p>
          <div className="flex items-center gap-2 mt-2.5">
            <button
              data-testid="pwa-install-btn"
              onClick={install}
              className="h-9 px-4 rounded-full bg-qv-primary text-white text-xs font-bold active:scale-95"
            >
              {platform === "ios" || (platform === "android" && !deferred) ? "Cómo instalar" : "Instalar app"}
            </button>
            <button
              onClick={dismiss}
              className="h-9 px-3 rounded-full bg-white/5 text-white/60 text-xs font-semibold"
            >
              Ahora no
            </button>
          </div>

          {showIosSteps && platform === "ios" && (
            <div className="mt-3 rounded-xl bg-black/30 border border-white/10 p-3 space-y-2">
              <p className="text-white/80 text-xs font-semibold">En iPhone/iPad (Safari):</p>
              <div className="flex items-center gap-2 text-white/70 text-xs">
                <span className="w-6 h-6 rounded-lg bg-white/10 flex items-center justify-center shrink-0">
                  <Share className="w-3.5 h-3.5" />
                </span>
                1. Pulsa el botón <b className="text-white">Compartir</b>.
              </div>
              <div className="flex items-center gap-2 text-white/70 text-xs">
                <span className="w-6 h-6 rounded-lg bg-white/10 flex items-center justify-center shrink-0">
                  <Plus className="w-3.5 h-3.5" />
                </span>
                2. Elige <b className="text-white">Añadir a pantalla de inicio</b>.
              </div>
              <p className="text-white/50 text-[11px]">3. Confirma con <b className="text-white">Añadir</b>. ¡Listo! 🎉</p>
            </div>
          )}

          {showIosSteps && platform !== "ios" && (
            <div className="mt-3 rounded-xl bg-black/30 border border-white/10 p-3 space-y-2">
              <p className="text-white/80 text-xs font-semibold">En Android (Chrome):</p>
              <div className="flex items-center gap-2 text-white/70 text-xs">
                <span className="w-6 h-6 rounded-lg bg-white/10 flex items-center justify-center shrink-0 font-bold">⋮</span>
                1. Abre el menú <b className="text-white">(⋮)</b> arriba a la derecha.
              </div>
              <div className="flex items-center gap-2 text-white/70 text-xs">
                <span className="w-6 h-6 rounded-lg bg-white/10 flex items-center justify-center shrink-0">
                  <Plus className="w-3.5 h-3.5" />
                </span>
                2. Elige <b className="text-white">Instalar app</b> o <b className="text-white">Añadir a pantalla de inicio</b>.
              </div>
              <p className="text-white/50 text-[11px]">3. Confirma. ¡Listo! 🎉</p>
            </div>
          )}
        </div>
        <button onClick={dismiss} className="text-white/40 shrink-0" aria-label="Cerrar">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
