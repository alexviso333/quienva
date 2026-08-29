import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isNativeApp } from "@/lib/platform";
import { X } from "lucide-react";

export const APP_STORE_URL =
  "https://apps.apple.com/es/app/qui%C3%A9n-va-fiestas-cerca/id6804396475";

const DISMISS_KEY = "qv_appstore_promo_dismissed";
const DISMISS_DAYS = 7;

function AppleLogo({ className = "w-5 h-5" }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M16.365 1.43c0 1.14-.42 2.2-1.12 3.03-.78.94-2.06 1.66-3.16 1.57-.14-1.1.42-2.28 1.09-3.02.76-.86 2.12-1.5 3.19-1.58zM20.9 17.02c-.55 1.27-.81 1.83-1.52 2.95-.99 1.56-2.39 3.5-4.12 3.51-1.54.02-1.94-1-4.03-.99-2.09.01-2.53 1.01-4.07.99-1.73-.02-3.05-1.78-4.04-3.34C1.28 16.62.99 12.02 2.68 9.6c1.02-1.46 2.62-2.31 4.13-2.31 1.54 0 2.5 1.02 3.77 1.02 1.23 0 1.98-1.02 3.76-1.02 1.34 0 2.76.73 3.78 1.99-3.32 1.82-2.78 6.56.98 7.74z" />
    </svg>
  );
}

/**
 * Eye-catching "Get the app on the App Store" banner for the WEB site
 * (quienva.me). Never shows inside the native app. Goal: drive App Store
 * installs. Dismissible for a week so loyal web users aren't nagged.
 */
export default function AppStorePromo() {
  const { i18n } = useTranslation();
  const [hidden, setHidden] = useState(() => {
    if (isNativeApp()) return true;
    try {
      const until = Number(localStorage.getItem(DISMISS_KEY) || 0);
      return until > Date.now();
    } catch {
      return false;
    }
  });

  if (hidden || isNativeApp()) return null;

  const lang = (i18n.language || "es").slice(0, 2);
  const T = {
    es: { title: "Descarga la app gratis", sub: "Todas las fiestas cerca de ti, en tu móvil", cta: "App Store" },
    en: { title: "Get the free app", sub: "Every party near you, on your phone", cta: "App Store" },
    de: { title: "Hol dir die App gratis", sub: "Alle Partys in deiner Nähe, auf dem Handy", cta: "App Store" },
  }[lang] || { title: "Descarga la app gratis", sub: "Todas las fiestas cerca de ti, en tu móvil", cta: "App Store" };

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now() + DISMISS_DAYS * 864e5));
    } catch {
      /* ignore */
    }
    setHidden(true);
  };

  return (
    <div className="px-4 pb-3" data-testid="appstore-promo">
      <div className="relative overflow-hidden rounded-3xl border border-white/15 bg-gradient-to-br from-black/70 via-qv-primary/25 to-qv-secondary/20 p-4 shadow-[0_18px_50px_-20px_rgba(255,0,85,0.55)]">
        <span className="pointer-events-none absolute -top-12 -right-8 w-44 h-44 rounded-full bg-qv-secondary/25 blur-2xl" />
        <button
          onClick={dismiss}
          aria-label="Cerrar"
          className="absolute top-2.5 right-2.5 z-10 w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white/70"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="relative flex items-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#141216] to-black border border-white/15 flex items-center justify-center shrink-0 shadow-lg">
            <span className="font-display font-black text-[13px] leading-none">
              <span className="text-white">¿Q</span>
              <span className="text-qv-primary">va?</span>
            </span>
          </div>
          <div className="min-w-0 pr-6">
            <div className="text-yellow-300 text-xs tracking-[3px] leading-none mb-1">★★★★★</div>
            <h3 className="font-display font-black text-white text-lg leading-tight">{T.title}</h3>
            <p className="text-white/70 text-[13px] leading-snug">{T.sub}</p>
          </div>
        </div>

        <a
          href={APP_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="relative mt-3 w-full h-12 rounded-full bg-black border border-white/25 text-white font-display font-bold text-[15px] flex items-center justify-center gap-2 active:scale-[0.99] transition-transform"
        >
          <AppleLogo /> {T.cta}
        </a>
      </div>
    </div>
  );
}
