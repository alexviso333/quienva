import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Users, ChevronRight, X, BarChart3 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import api from "@/lib/api";
import GroupInviteStep from "@/components/GroupInviteStep";

// Small, attention-grabbing "Crea e invita a tu grupo" banner on the Feed. Shows
// ONLY for logged-in users who don't have a group yet, and can be dismissed.
// Tapping it opens a clean modal with the 2-phase group create + invite flow so
// the feed itself stays compact.
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

  const dismiss = (e) => {
    e?.stopPropagation();
    localStorage.setItem("qv_monta_grupo_dismissed", "1");
    setDismissed(true);
  };

  return (
    <>
      <div
        data-testid="monta-grupo-banner"
        className="w-full rounded-2xl border border-qv-primary/40 bg-gradient-to-r from-qv-primary/15 to-qv-secondary/12 p-3 flex items-center gap-3"
      >
        <div className="w-10 h-10 rounded-full bg-qv-primary/20 flex items-center justify-center shrink-0">
          <BarChart3 className="w-5 h-5 text-qv-primary" />
        </div>
        <button
          type="button"
          data-testid="monta-grupo-open"
          onClick={() => setOpen(true)}
          className="flex-1 min-w-0 text-left active:scale-[0.99] transition-transform"
        >
          <p className="font-display font-black text-white text-sm leading-tight">
            {t("montagrupo.title", "Cread vuestra encuesta de a dónde ir")}
          </p>
          <p className="text-white/60 text-xs leading-tight truncate">
            {t("montagrupo.sub", "Monta un grupo y decidid juntos la fiesta con una encuesta")}
          </p>
        </button>
        <button
          type="button"
          data-testid="monta-grupo-open-cta"
          onClick={() => setOpen(true)}
          className="shrink-0 text-xs font-bold text-white bg-qv-primary rounded-full px-3.5 py-2 active:scale-95 flex items-center gap-1"
        >
          {t("montagrupo.cta", "Crear")} <ChevronRight className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          data-testid="monta-grupo-dismiss"
          onClick={dismiss}
          aria-label={t("feed.dismiss", "Cerrar")}
          className="shrink-0 text-white/40 active:scale-90"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-[#121215] border-white/10 text-white max-w-sm rounded-2xl" data-testid="monta-grupo-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="w-5 h-5 text-qv-primary" /> {t("groupinvite.title", "Monta tu grupo")}
            </DialogTitle>
          </DialogHeader>
          <p className="text-white/60 text-sm -mt-1 mb-1 leading-relaxed">
            {t("montagrupo.dialog_sub", "Ponle nombre y crea tu grupo: dentro podréis lanzar una encuesta de a dónde ir.")}
          </p>
          <GroupInviteStep />
        </DialogContent>
      </Dialog>
    </>
  );
}
