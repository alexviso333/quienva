import { useTranslation } from "react-i18next";
import { ClipboardList, ChevronRight } from "lucide-react";
import { API } from "@/lib/api";
import { captureEvent } from "@/analytics/posthog";

// Permanent, non-dismissable banner above "Esta noche": the primary entry point
// to create a shareable Plan (/p/nuevo). Links to the backend-rendered page.
export default function MontaPlanBanner({ city }) {
  const { t } = useTranslation();
  const go = () => {
    captureEvent("plan_create_started", { source: "feed" });
    const q = city ? `?ciudad=${encodeURIComponent(city)}` : "";
    window.location.href = `${API}/p/nuevo${q}`;
  };
  return (
    <button
      type="button"
      data-testid="monta-plan-banner"
      onClick={go}
      className="w-full text-left rounded-2xl border border-qv-primary/50 bg-gradient-to-r from-qv-primary/25 via-qv-primary/10 to-qv-secondary/15 p-3.5 flex items-center gap-3 active:scale-[0.99] transition-transform"
    >
      <div className="w-11 h-11 rounded-2xl bg-qv-primary/25 flex items-center justify-center shrink-0">
        <ClipboardList className="w-5.5 h-5.5 text-qv-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-display font-black text-white text-[15px] leading-tight">
          {t("montaplan.title", "Monta tu plan para esta noche")}
        </p>
        <p className="text-white/65 text-xs leading-tight">
          {t("montaplan.sub", "Pon opciones, mira quién se apunta y cerradlo entre todos")}
        </p>
      </div>
      <span className="shrink-0 text-xs font-bold text-black bg-qv-primary rounded-full px-3.5 py-2 flex items-center gap-1">
        {t("montaplan.cta", "Crear")} <ChevronRight className="w-3.5 h-3.5" />
      </span>
    </button>
  );
}
