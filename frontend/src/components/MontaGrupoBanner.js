import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Users, ChevronRight, X } from "lucide-react";
import api from "@/lib/api";
import GroupInviteStep from "@/components/GroupInviteStep";

// Discreet, permanent "Monta tu grupo" access on the Feed. Only shows for users
// who don't have a group yet, and can be dismissed. Tapping it expands the group
// creation + WhatsApp-invite flow inline (no page change) so it never feels
// intrusive.
export default function MontaGrupoBanner() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem("qv_monta_grupo_dismissed") === "1"
  );

  const { data: groups } = useQuery({
    queryKey: ["groups"],
    queryFn: async () => (await api.get("/groups")).data,
    staleTime: 60_000,
  });

  // Hide once the user already belongs to at least one group, or dismissed it.
  if (dismissed || (Array.isArray(groups) && groups.length > 0)) return null;

  const dismiss = () => {
    localStorage.setItem("qv_monta_grupo_dismissed", "1");
    setDismissed(true);
  };

  return (
    <div
      className="rounded-2xl border border-qv-primary/30 bg-gradient-to-br from-qv-primary/12 via-white/[0.03] to-transparent p-4"
      data-testid="monta-grupo-banner"
    >
      {!open ? (
        <button
          type="button"
          data-testid="monta-grupo-open"
          onClick={() => setOpen(true)}
          className="w-full flex items-center gap-3 text-left active:scale-[0.99] transition-transform"
        >
          <div className="w-11 h-11 rounded-full bg-qv-primary/20 flex items-center justify-center flex-shrink-0">
            <Users className="w-5 h-5 text-qv-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-display font-black text-white text-base">{t("groupinvite.title", "Monta tu grupo")}</p>
            <p className="text-white/55 text-xs leading-tight">
              {t("groupinvite.banner_sub", "Trae a tu gente de un toque y ved a qué va cada uno")}
            </p>
          </div>
          <ChevronRight className="w-5 h-5 text-white/40 flex-shrink-0" />
        </button>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <p className="font-display font-black text-white text-base flex items-center gap-2">
              <Users className="w-4 h-4 text-qv-primary" /> {t("groupinvite.title", "Monta tu grupo")}
            </p>
            <button
              type="button"
              data-testid="monta-grupo-close"
              onClick={dismiss}
              aria-label="Cerrar"
              className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <GroupInviteStep />
        </div>
      )}
    </div>
  );
}
