import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ClipboardList, Users, ArrowRight, Clock } from "lucide-react";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Collect the slugs of plans this device created (stored as qv_ct_<slug> by
// CreatePlanSheet). Lets guests see "their" open plans without an account.
function myCreatedSlugs() {
  const out = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith("qv_ct_")) out.push(k.slice(6));
    }
  } catch (e) { /* ignore */ }
  return out;
}

function closesLabel(hora_limite, t) {
  if (!hora_limite) return null;
  try {
    const d = new Date(hora_limite);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return t("myplans.closes_at", "cierra {{time}}", { time: `${hh}:${mm}` });
  } catch (e) { return null; }
}

// Feed section: the viewer's OPEN shareable plans (as creator or participant),
// so they can jump back in. Hidden entirely when there are none. (Spec 4.1)
export default function MyOpenPlans() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const slugs = myCreatedSlugs();

  const { data } = useQuery({
    queryKey: ["my-open-plans", slugs.join(","), user?.user_id || "guest"],
    queryFn: async () => (await api.get(`/plans/mine?slugs=${encodeURIComponent(slugs.join(","))}`)).data,
    enabled: slugs.length > 0 || !!user,
    staleTime: 20000,
  });

  const plans = data?.plans || [];
  if (!plans.length) return null;

  return (
    <section data-testid="feed-my-plans">
      <h2 className="text-lg font-black text-white flex items-center gap-2 font-display mb-3">
        <ClipboardList className="w-5 h-5 text-qv-primary" /> {t("myplans.title", "Tus planes abiertos")}
      </h2>
      <div className="flex gap-3 overflow-x-auto hide-scrollbar -mx-4 px-4 pb-1 snap-x">
        {plans.map((p) => {
          const pct = p.umbral_personas ? Math.min(100, Math.round((p.dentro / p.umbral_personas) * 100)) : null;
          const closes = closesLabel(p.hora_limite, t);
          return (
            <a
              key={p.slug}
              href={`${API}/p/${p.slug}`}
              data-testid={`my-plan-${p.slug}`}
              className="snap-start shrink-0 w-[230px] rounded-2xl border border-qv-primary/30 bg-gradient-to-br from-qv-primary/12 via-white/[0.03] to-transparent p-3.5 active:scale-[0.99] transition-transform"
            >
              <p className="text-sm font-bold text-white truncate">{p.titulo}</p>
              <p className="text-[11px] text-white/55 flex items-center gap-1 mt-0.5">
                <Users className="w-3 h-3" />
                {p.umbral_personas
                  ? t("myplans.inside_quorum", "{{dentro}}/{{umbral}} dentro", { dentro: p.dentro, umbral: p.umbral_personas })
                  : t("myplans.inside", "{{dentro}} dentro", { dentro: p.dentro })}
                {closes ? <><span className="text-white/25">·</span><Clock className="w-3 h-3" />{closes}</> : null}
              </p>
              {pct !== null && (
                <div className="h-1.5 rounded-full bg-white/10 overflow-hidden mt-2.5">
                  <div className="h-full bg-gradient-to-r from-qv-primary to-[#8b5cf6] rounded-full transition-all" style={{ width: `${pct}%` }} />
                </div>
              )}
              <span className="mt-2.5 inline-flex items-center gap-1 text-xs font-bold text-qv-primary">
                {t("myplans.view", "Ver plan")} <ArrowRight className="w-3.5 h-3.5" />
              </span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
