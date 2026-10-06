import { useTranslation } from "react-i18next";
import { ClipboardList, ChevronRight } from "lucide-react";
import { useCreatePlan } from "@/context/CreatePlan";

// Subtle, feed-native entry point to create a shareable Plan.
// Opens the in-app CreatePlanSheet (bottom sheet) — never leaves the app.
export default function MontaPlanBanner({ city }) {
  const { t } = useTranslation();
  const { open } = useCreatePlan();
  const go = () => open(null, city, "feed");
  return (
    <button
      type="button"
      data-testid="monta-plan-banner"
      onClick={go}
      className="w-full text-left rounded-2xl border border-white/10 bg-white/[0.04] px-3.5 py-3 flex items-center gap-3 active:scale-[0.99] transition-transform hover:border-white/20"
    >
      <div className="w-9 h-9 rounded-xl bg-qv-primary/15 border border-qv-primary/30 flex items-center justify-center shrink-0">
        <ClipboardList className="w-[18px] h-[18px] text-qv-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-white text-sm leading-tight">
          {t("montaplan.title", "Crea un plan y mira quién se apunta")}
        </p>
        <p className="text-white/50 text-xs leading-tight truncate">
          {t("montaplan.sub", "Propón 1-3 sitios y compártelo por WhatsApp")}
        </p>
      </div>
      <span className="shrink-0 text-xs font-bold text-qv-primary flex items-center gap-0.5">
        {t("montaplan.cta", "Crear")} <ChevronRight className="w-3.5 h-3.5" />
      </span>
    </button>
  );
}
