import { useTranslation } from "react-i18next";
import { ClipboardList, ChevronRight } from "lucide-react";
import { useCreatePlan } from "@/context/CreatePlan";

// Subtle, feed-native entry point to create a shareable Plan.
// Opens the in-app CreatePlanSheet (bottom sheet) — never leaves the app.
// Kept as a light single-line row so it informs without crowding the feed top.
export default function MontaPlanBanner({ city }) {
  const { t } = useTranslation();
  const { open } = useCreatePlan();
  const go = () => open(null, city, "feed");
  return (
    <button
      type="button"
      data-testid="monta-plan-banner"
      onClick={go}
      className="w-full text-left rounded-full border border-white/10 bg-white/[0.03] pl-3 pr-3.5 py-2 flex items-center gap-2.5 active:scale-[0.99] transition-transform hover:border-qv-primary/30"
    >
      <ClipboardList className="w-4 h-4 text-qv-primary shrink-0" />
      <span className="flex-1 min-w-0 truncate text-sm font-semibold text-white/85">
        {t("montaplan.title", "Crea un plan y mira quién se apunta")}
      </span>
      <span className="shrink-0 text-xs font-bold text-qv-primary flex items-center gap-0.5">
        {t("montaplan.cta", "Crear")} <ChevronRight className="w-3.5 h-3.5" />
      </span>
    </button>
  );
}
