import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Ticket, CheckCircle2, XCircle, Loader2, RefreshCw, ChevronDown, ChevronRight,
  Bell, BellOff, Euro, Link2,
} from "lucide-react";

function whenText(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

function fmtDate(d) {
  try {
    return new Date(d + "T00:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short" });
  } catch {
    return d;
  }
}

/**
 * Cobertura ClubTickets — solo admin.
 * Muestra, por discoteca, qué fiestas de TU panel de afiliado están vivas en la
 * app con tu enlace (emparejadas) y cuáles faltan (sin emparejar). Incluye el
 * interruptor de la "Alerta de desajuste" (aviso cuando una fiesta cambia de
 * enlace afiliado <-> directo tras un re-escaneo).
 */
export default function AdminClubTicketsCoverage() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState({});

  const { data, isLoading } = useQuery({
    queryKey: ["admin-clubtickets-coverage"],
    queryFn: async () => (await api.get("/admin/clubtickets-coverage")).data,
    staleTime: 60_000,
  });

  const { data: flipData } = useQuery({
    queryKey: ["admin-flip-alerts"],
    queryFn: async () => (await api.get("/admin/settings/affiliate-flip-alerts")).data,
    staleTime: 60_000,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-clubtickets-coverage"] });

  const toggleFlip = useMutation({
    mutationFn: async (enabled) => (await api.put("/admin/settings/affiliate-flip-alerts", { enabled })).data,
    onSuccess: (d) => {
      toast.success(d.enabled ? "Alerta de desajuste activada" : "Alerta de desajuste desactivada");
      qc.invalidateQueries({ queryKey: ["admin-flip-alerts"] });
    },
    onError: () => toast.error("No se pudo cambiar la alerta"),
  });

  const totals = data?.totals || { parties: 0, matched: 0, unmatched: 0, with_price: 0 };
  const venues = data?.venues || [];
  const flipEnabled = flipData?.enabled !== false;

  return (
    <div className="rounded-3xl bg-white/[0.03] border border-white/10 p-4 mb-6" data-testid="admin-clubtickets-coverage">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Ticket className="w-4 h-4 text-qv-secondary" />
          <h3 className="font-display font-black text-white text-sm uppercase tracking-wide">Cobertura ClubTickets</h3>
        </div>
        <button
          onClick={refresh}
          className="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center active:scale-90"
          title="Actualizar"
          data-testid="coverage-refresh"
        >
          <RefreshCw className="w-4 h-4 text-white/70" />
        </button>
      </div>

      {/* Alerta de desajuste toggle */}
      <button
        onClick={() => toggleFlip.mutate(!flipEnabled)}
        disabled={toggleFlip.isPending}
        className="w-full flex items-center gap-2.5 p-2.5 mb-3 rounded-xl bg-white/[0.03] border border-white/10 active:scale-[0.99]"
        data-testid="flip-alert-toggle"
      >
        <span className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${flipEnabled ? "bg-amber-400/15 text-amber-300" : "bg-white/10 text-white/40"}`}>
          {flipEnabled ? <Bell className="w-3.5 h-3.5" /> : <BellOff className="w-3.5 h-3.5" />}
        </span>
        <div className="flex-1 min-w-0 text-left">
          <p className="text-white text-xs font-semibold">Alerta de desajuste</p>
          <p className="text-white/40 text-[10px]">Avísame cuando una fiesta cambie de enlace afiliado ↔ directo</p>
        </div>
        <span className={`shrink-0 w-9 h-5 rounded-full relative transition-colors ${flipEnabled ? "bg-amber-400/70" : "bg-white/15"}`}>
          <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${flipEnabled ? "left-4" : "left-0.5"}`} />
        </span>
      </button>

      {data && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full text-white/70 bg-white/10">
            <Link2 className="w-3 h-3" /> {totals.parties} fiestas ({data.aff_code})
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full text-emerald-300 bg-emerald-400/15">
            <CheckCircle2 className="w-3 h-3" /> {totals.matched} emparejadas
          </span>
          {totals.unmatched > 0 && (
            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full text-red-300 bg-red-400/15">
              <XCircle className="w-3 h-3" /> {totals.unmatched} sin emparejar
            </span>
          )}
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full text-sky-300 bg-sky-400/15">
            <Euro className="w-3 h-3" /> {totals.with_price} con precio real
          </span>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
      ) : venues.length === 0 ? (
        <p className="text-white/40 text-xs italic py-3">Sin fiestas en tu panel de ClubTickets (o el panel no responde).</p>
      ) : (
        <div className="space-y-1.5">
          {venues.map((v) => {
            const isOpen = !!expanded[v.slug];
            const gap = (v.unmatched || 0) > 0;
            return (
              <div key={v.slug} className={`rounded-xl border ${gap ? "bg-red-500/[0.06] border-red-400/30" : "bg-white/[0.03] border-white/5"}`} data-testid={`coverage-venue-${v.slug}`}>
                <button
                  onClick={() => setExpanded((s) => ({ ...s, [v.slug]: !s[v.slug] }))}
                  className="w-full flex items-center gap-2.5 p-2.5 text-left"
                >
                  {isOpen ? <ChevronDown className="w-4 h-4 text-white/50 shrink-0" /> : <ChevronRight className="w-4 h-4 text-white/50 shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-xs font-semibold truncate">{v.name}</p>
                    <p className="text-white/40 text-[10px]">{v.total} fiestas</p>
                  </div>
                  <span className="text-emerald-300 text-[10px] font-bold shrink-0 bg-emerald-400/15 rounded-full px-2 py-0.5">{v.matched} ✓</span>
                  {gap && <span className="text-red-300 text-[10px] font-bold shrink-0 bg-red-400/20 rounded-full px-2 py-0.5">{v.unmatched} ✗</span>}
                </button>
                {isOpen && (
                  <div className="px-2.5 pb-2.5 space-y-1">
                    {v.parties.map((p, i) => {
                      let badge, badgeCls;
                      if (!p.matched) { badge = "Sin emparejar"; badgeCls = "text-red-300 bg-red-400/15"; }
                      else if (p.has_price) { badge = "Con precio"; badgeCls = "text-emerald-300 bg-emerald-400/15"; }
                      else { badge = "Solo ClubTickets"; badgeCls = "text-sky-300 bg-sky-400/15"; }
                      return (
                        <div key={i} className="flex items-center gap-2 py-1 border-t border-white/5 first:border-t-0" data-testid={`coverage-party-${v.slug}-${i}`}>
                          <span className="text-white/40 text-[10px] w-14 shrink-0 tabular-nums">{fmtDate(p.date)}</span>
                          <span className="flex-1 min-w-0 text-white/85 text-[11px] truncate">{p.name}</span>
                          <span className={`shrink-0 text-[9px] font-bold rounded-full px-1.5 py-0.5 ${badgeCls}`}>{badge}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {data?.updated_at && (
        <p className="text-white/30 text-[10px] mt-3">Panel act. {whenText(data.updated_at)} · verde = con precio real · azul = solo ClubTickets · rojo = falta en la app</p>
      )}
    </div>
  );
}
