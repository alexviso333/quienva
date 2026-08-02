import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import {
  Sparkles, TrendingUp, TrendingDown, Ticket, Flame, Lock, Loader2, RefreshCw,
} from "lucide-react";

const KIND_META = {
  new: { label: "Nueva fiesta", icon: Sparkles, cls: "text-emerald-300 bg-emerald-400/15" },
  price_up: { label: "Sube precio", icon: TrendingUp, cls: "text-orange-300 bg-orange-400/15" },
  price_down: { label: "Baja precio", icon: TrendingDown, cls: "text-sky-300 bg-sky-400/15" },
  on_sale: { label: "A la venta", icon: Ticket, cls: "text-emerald-300 bg-emerald-400/15" },
  state: { label: "Pocas entradas", icon: Flame, cls: "text-orange-300 bg-orange-400/15" },
  sold_out: { label: "Agotado", icon: Lock, cls: "text-white/60 bg-white/10" },
};

function whenText(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/**
 * Novedades del último scrapeo — solo admin. Ligero: una sola query cacheada.
 */
export default function AdminScrapeChangelog() {
  const navigate = useNavigate();
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["admin-scrape-changelog"],
    queryFn: async () => (await api.get("/admin/scrape-changelog?limit=80")).data,
    staleTime: 60_000,
  });

  const entries = data?.entries || [];
  const counts = data?.counts || {};
  const last = data?.last_run;

  return (
    <div className="rounded-3xl bg-white/[0.03] border border-white/10 p-4 mb-6" data-testid="admin-scrape-changelog">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-qv-secondary" />
          <h3 className="font-display font-black text-white text-sm uppercase tracking-wide">Novedades del scrapeo</h3>
        </div>
        <button
          onClick={() => refetch()}
          className="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center active:scale-90"
          title="Actualizar"
          data-testid="changelog-refresh"
        >
          <RefreshCw className={`w-4 h-4 text-white/70 ${isFetching ? "animate-spin" : ""}`} />
        </button>
      </div>

      {last?.at && (
        <p className="text-white/40 text-[11px] mb-3">
          Última pasada: {whenText(last.at)} · {last.venues_run} locales · {last.total_new} nuevas · {last.total_updated} actualizadas
        </p>
      )}

      {/* counters */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {Object.entries(counts).filter(([, v]) => v > 0).map(([k, v]) => {
          const meta = KIND_META[k] || KIND_META.state;
          const Icon = meta.icon;
          return (
            <span key={k} className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full ${meta.cls}`}>
              <Icon className="w-3 h-3" /> {v} {meta.label}
            </span>
          );
        })}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
      ) : entries.length === 0 ? (
        <p className="text-white/40 text-xs italic py-3">Sin cambios en la última pasada del scrapeo.</p>
      ) : (
        <div className="space-y-1.5 max-h-72 overflow-y-auto hide-scrollbar">
          {entries.map((e) => {
            const meta = KIND_META[e.kind] || KIND_META.state;
            const Icon = meta.icon;
            let detail = "";
            if (e.kind === "price_up" && e.new_price != null) detail = `→ ${Math.round(e.new_price)}€`;
            else if (e.kind === "price_down" && e.new_price != null) detail = `→ desde ${Math.round(e.new_price)}€`;
            else if (e.new_state) detail = `→ ${e.new_state.replace(/_/g, " ")}`;
            return (
              <button
                key={e.id}
                onClick={() => e.event_id && navigate(`/event/${e.event_id}`)}
                className="w-full flex items-center gap-2.5 p-2 rounded-xl bg-white/[0.03] border border-white/5 text-left active:scale-[0.99]"
                data-testid={`changelog-entry-${e.id}`}
              >
                <span className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${meta.cls}`}>
                  <Icon className="w-3.5 h-3.5" />
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-xs font-semibold truncate">{e.event_name || "—"} {detail && <span className="text-white/50 font-normal">{detail}</span>}</p>
                  <p className="text-white/40 text-[10px] truncate">{e.venue} · {e.date}</p>
                </div>
                <span className="text-white/30 text-[9px] shrink-0">{whenText(e.created_at)}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
