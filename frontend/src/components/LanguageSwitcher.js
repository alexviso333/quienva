import { useTranslation } from "react-i18next";

const LANGS = [
  { code: "es", label: "ES" },
  { code: "en", label: "EN" },
  { code: "de", label: "DE" },
];

// Compact ES / EN / DE pill. Persists the choice via i18next languageDetector
// (localStorage 'qv_lang'). Drop it anywhere (Login, Settings, top bar).
export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();
  const current = (i18n.resolvedLanguage || i18n.language || "es").slice(0, 2);
  return (
    <div
      className={`inline-flex items-center gap-1 p-1 rounded-full bg-white/5 border border-white/10 ${className}`}
      data-testid="lang-switcher"
    >
      {LANGS.map((l) => (
        <button
          key={l.code}
          type="button"
          data-testid={`lang-${l.code}`}
          onClick={() => i18n.changeLanguage(l.code)}
          className={`px-2.5 h-7 rounded-full text-xs font-bold transition-colors ${
            current === l.code ? "bg-white text-black" : "text-white/60"
          }`}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
