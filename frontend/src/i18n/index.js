import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import es from "./locales/es.json";
import en from "./locales/en.json";
import de from "./locales/de.json";

// Quienva i18n. Adding a language never breaks existing screens: any string that
// is not yet migrated to t() keeps rendering its original Spanish text.
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      es: { translation: es },
      en: { translation: en },
      de: { translation: de },
    },
    fallbackLng: "es",
    supportedLngs: ["es", "en", "de"],
    nonExplicitSupportedLngs: true, // de-DE -> de, en-GB -> en
    load: "languageOnly",
    interpolation: { escapeValue: false },
    detection: {
      // Remember the user's manual choice; otherwise fall back to the browser
      // language (perfect for German/British tourists in Mallorca/Ibiza).
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "qv_lang",
      caches: ["localStorage"],
    },
    react: { useSuspense: false },
  });

export default i18n;
