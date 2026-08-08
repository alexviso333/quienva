import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import api, { mediaThumb } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { ArrowLeft, Images, Calendar, Loader2, ChevronRight, PartyPopper } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

const LOCALE_BY_LANG = { es: "es-ES", en: "en-GB", de: "de-DE" };
const dateLocale = () => LOCALE_BY_LANG[(i18n.language || "es").slice(0, 2)] || "es-ES";

function fmtDate(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString(dateLocale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function monthKey(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString(dateLocale(), { month: "long", year: "numeric" });
  } catch {
    return "";
  }
}

/**
 * Fiestas pasadas — las fiestas a las que fuiste (Voy/Estuve) ya celebradas.
 * Tocar una entra en su ficha, donde está el álbum compartido + privado.
 */
export default function PastParties() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const { data, isLoading } = useQuery({
    queryKey: ["past-events"],
    queryFn: async () => (await api.get("/me/past-events")).data,
    staleTime: 60000,
  });

  const items = data?.items || [];

  // group by month for a clean timeline
  const groups = [];
  let currentKey = null;
  items.forEach((it) => {
    const k = monthKey(it.date);
    if (k !== currentKey) {
      groups.push({ key: k, items: [] });
      currentKey = k;
    }
    groups[groups.length - 1].items.push(it);
  });

  return (
    <AppShell>
      <div className="px-4 pt-5">
        <header className="flex items-center gap-3 mb-5">
          <button
            data-testid="past-back"
            onClick={() => navigate(-1)}
            className="w-10 h-10 rounded-full border border-white/15 flex items-center justify-center active:scale-90"
          >
            <ArrowLeft className="w-5 h-5 text-white" />
          </button>
          <div>
            <h1 className="font-display font-black text-2xl text-white leading-none">{t("pastparties.title")}</h1>
            <p className="text-white/50 text-xs mt-1">{t("pastparties.subtitle")}</p>
          </div>
        </header>

        {isLoading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
        ) : items.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-white/15 bg-white/[0.02] p-8 text-center mt-6">
            <PartyPopper className="w-10 h-10 text-white/30 mx-auto mb-3" />
            <p className="text-white/60 text-sm font-semibold mb-1">{t("recuerdos.empty_title")}</p>
            <p className="text-white/40 text-xs mb-4">
              {t("pastparties.empty_body")}
            </p>
            <button
              onClick={() => navigate("/feed")}
              className="h-10 px-5 rounded-full bg-qv-primary text-white font-bold text-sm active:scale-95"
            >
              {t("recuerdos.see_plans")}
            </button>
          </div>
        ) : (
          <div className="space-y-6 pb-6">
            {groups.map((g) => (
              <div key={g.key}>
                <p className="text-white/40 text-[11px] uppercase tracking-widest font-bold mb-2 capitalize">{g.key}</p>
                <div className="space-y-2.5">
                  {g.items.map((it, i) => (
                    <motion.button
                      key={it.id}
                      data-testid={`past-party-${it.id}`}
                      onClick={() => navigate(`/event/${it.id}`)}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, delay: Math.min(i * 0.03, 0.2) }}
                      className="w-full flex items-center gap-3 p-2 rounded-2xl bg-[#121215] border border-white/10 text-left active:scale-[0.99] transition-transform"
                    >
                      <div className="w-16 h-16 rounded-xl overflow-hidden bg-black shrink-0">
                        {it.image_url ? (
                          <img src={mediaThumb(it.image_url, 200)} alt="" className="w-full h-full object-cover" loading="lazy" />
                        ) : (
                          <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] to-[#0a1a1f]" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-display font-bold text-white text-sm leading-tight line-clamp-1">{it.name}</p>
                        <p className="text-white/50 text-xs mt-0.5 flex items-center gap-1 capitalize">
                          <Calendar className="w-3 h-3" /> {fmtDate(it.date)}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${it.my_status === "estuve" ? "bg-qv-secondary/20 text-qv-secondary" : "bg-qv-primary/20 text-qv-primary"}`}>
                            {it.my_status === "estuve" ? t("recuerdos.status_estuve") : t("recuerdos.status_fui")}
                          </span>
                          {it.my_photos > 0 && (
                            <span className="text-[10px] text-white/60 flex items-center gap-1">
                              <Images className="w-3 h-3" /> {it.my_photos}
                            </span>
                          )}
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-white/30 shrink-0" />
                    </motion.button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
