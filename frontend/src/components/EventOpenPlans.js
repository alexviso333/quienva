import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Users, ArrowRight } from "lucide-react";
import api from "@/lib/api";

// Shows the active shareable Plans (/p/{slug}) created for this event, so people
// can join an existing plan instead of starting from scratch. Amplifies the
// viral Plan object on the event detail page.
export function EventOpenPlans({ eventId }) {
  const { data } = useQuery({
    queryKey: ["event-plans", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/plans`)).data,
    enabled: !!eventId,
    staleTime: 30000,
  });

  const plans = data?.plans || [];
  if (!plans.length) return null;

  return (
    <div className="mt-5" data-testid="event-open-plans">
      <h3 className="text-sm font-black uppercase tracking-wider text-white/70 mb-3 flex items-center gap-2">
        <ClipboardList className="w-4 h-4 text-qv-primary" /> Planes abiertos para esta fiesta
      </h3>
      <div className="flex flex-col gap-2.5">
        {plans.map((p) => {
          const dentro = p.dentro || 0;
          const pct = p.umbral_personas
            ? Math.min(100, Math.round((dentro / p.umbral_personas) * 100))
            : null;
          return (
            <Link
              key={p.slug}
              to={`/plan/${p.slug}`}
              data-testid={`event-plan-${p.slug}`}
              className="block rounded-2xl border border-white/12 bg-white/[0.05] p-3.5 active:scale-[0.99] transition-transform hover:border-qv-primary/40"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-qv-primary to-[#8b5cf6] flex items-center justify-center text-white font-bold shrink-0">
                  {(p.creador_apodo || "?").slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-white truncate">{p.titulo}</p>
                  <p className="text-[11px] text-white/55 flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    {p.umbral_personas
                      ? `${dentro}/${p.umbral_personas} dentro`
                      : `${dentro} dentro`}
                    {p.creador_apodo ? ` · de ${p.creador_apodo}` : ""}
                  </p>
                </div>
                <span className="text-xs font-bold text-qv-primary flex items-center gap-1 shrink-0">
                  Unirme <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
              {pct !== null && (
                <div className="h-1.5 rounded-full bg-white/10 overflow-hidden mt-2.5">
                  <div
                    className="h-full bg-gradient-to-r from-qv-primary to-[#8b5cf6] rounded-full"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default EventOpenPlans;
