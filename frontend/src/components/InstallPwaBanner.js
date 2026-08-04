import { useEffect, useState, useCallback } from "react";
import { Download, X, Share, Plus } from "lucide-react";

const DISMISS_KEY = "qv_pwa_dismissed_v1";

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
    if (localStorage.getItem(DISMISS_KEY) === "1") return;

    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferred(e);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // iOS never fires beforeinstallprompt, so surface the manual steps there.
    if (platform === "ios") setVisible(true);

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, [platform]);

  const dismiss = useCallback(() => {
    localStorage.setItem(DISMISS_KEY, "1");
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
    }
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
              {platform === "ios" ? "Cómo instalar" : "Instalar app"}
            </button>
            <button
              onClick={dismiss}
              className="h-9 px-3 rounded-full bg-white/5 text-white/60 text-xs font-semibold"
            >
              Ahora no
            </button>
          </div>

          {showIosSteps && (
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
        </div>
        <button onClick={dismiss} className="text-white/40 shrink-0" aria-label="Cerrar">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
