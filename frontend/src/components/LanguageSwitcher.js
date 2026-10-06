import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Check } from "lucide-react";

const LANGS = [
  { code: "es", label: "ES", name: "Español" },
  { code: "en", label: "EN", name: "English" },
  { code: "de", label: "DE", name: "Deutsch" },
];

// Language picker. Default = full ES/EN/DE pill (Login, Settings).
// compact = single globe button + dropdown (keeps the feed top bar light).
export default function LanguageSwitcher({ className = "", compact = false }) {
  const { i18n } = useTranslation();
  const current = (i18n.resolvedLanguage || i18n.language || "es").slice(0, 2);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  if (!compact) {
    return (
      <div className={`inline-flex items-center gap-1 p-1 rounded-full bg-white/5 border border-white/10 ${className}`} data-testid="lang-switcher">
        {LANGS.map((l) => (
          <button
            key={l.code}
            type="button"
            data-testid={`lang-${l.code}`}
            onClick={() => i18n.changeLanguage(l.code)}
            className={`px-2.5 h-7 rounded-full text-xs font-bold transition-colors ${current === l.code ? "bg-white text-black" : "text-white/60"}`}
          >
            {l.label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className={`relative ${className}`} ref={ref} data-testid="lang-switcher">
      <button
        type="button"
        data-testid="lang-compact-btn"
        onClick={() => setOpen((v) => !v)}
        aria-label="Idioma"
        className="flex items-center gap-1 w-9 h-9 justify-center text-white bg-white/[0.08] border border-white/10 rounded-full active:scale-95"
      >
        <Globe className="w-4 h-4 text-qv-secondary" />
      </button>
      {open && (
        <div className="absolute right-0 mt-2 z-30 w-36 rounded-2xl bg-[#17121f] border border-white/12 shadow-xl overflow-hidden py-1">
          {LANGS.map((l) => (
            <button
              key={l.code}
              type="button"
              data-testid={`lang-${l.code}`}
              onClick={() => { i18n.changeLanguage(l.code); setOpen(false); }}
              className="w-full flex items-center justify-between px-3.5 py-2.5 text-sm text-white/85 active:bg-white/5"
            >
              <span>{l.name}</span>
              {current === l.code ? <Check className="w-4 h-4 text-qv-secondary" /> : <span className="text-[10px] font-bold text-white/40">{l.label}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
