import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { toast } from "sonner";
import { Link2, CheckCircle2, MapPin, Loader2, RefreshCw } from "lucide-react";

function whenText(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

/**
 * Estado de afiliado FourVenues — solo admin.
 * Muestra los sitios/ciudades de TU slug y cuáles faltan por añadir a la app.
 */
export default function AdminAffiliatePanel() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-affiliate-status"],
    queryFn: async () => (await api.get("/admin/affiliate-status")).data,
    staleTime: 60_000,
  });

  const refresh = useMutation({
    mutationFn: async () => (await api.post("/admin/affiliate-refresh")).data,
    onSuccess: () => {
      toast.success("Afiliado actualizado");
      qc.invalidateQueries({ queryKey: ["admin-affiliate-status"] });
    },
    onError: () => toast.error("Error al actualizar"),
  });

  const venues = data?.venues || [];
  const inApp = venues.filter((v) => v.in_app);
  const pending = venues.filter((v) => !v.in_app);

  const VenueRow = (v, i, pendingRow) => (
    <div
      key={`${v.venue}-${v.city}-${i}`}
      className="flex items-center gap-2.5 p-2 rounded-xl bg-white/[0.03] border border-white/5"
      data-testid={`affiliate-venue-${pendingRow ? "pending" : "inapp"}-${i}`}
    >
      <span className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${pendingRow ? "bg-orange-400/15 text-orange-300" : "bg-emerald-400/15 text-emerald-300"}`}>
        {pendingRow ? <MapPin className="w-3.5 h-3.5" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-white text-xs font-semibold truncate">{v.venue}</p>
        <p className="text-white/40 text-[10px] truncate">{v.city || "Ciudad desconocida"}</p>
      </div>
      <span className="text-white/50 text-[10px] font-bold shrink-0 bg-white/5 rounded-full px-2 py-0.5">{v.events} {v.events === 1 ? "fiesta" : "fiestas"}</span>
    </div>
  );

  return (
    <div className="rounded-3xl bg-white/[0.03] border border-white/10 p-4 mb-6" data-testid="admin-affiliate-panel">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Link2 className="w-4 h-4 text-qv-secondary" />
          <h3 className="font-display font-black text-white text-sm uppercase tracking-wide">Afiliado FourVenues</h3>
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center active:scale-90"
          title="Actualizar ahora"
          data-testid="affiliate-refresh"
        >
          <RefreshCw className={`w-4 h-4 text-white/70 ${refresh.isPending ? "animate-spin" : ""}`} />
        </button>
      </div>

      {data && (
        <p className="text-white/40 text-[11px] mb-3">
          Slug <span className="text-qv-secondary font-semibold">{data.slug}</span> · {data.mine_count} fiestas tuyas · {venues.length} locales · act. {whenText(data.updated_at)}
        </p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
      ) : venues.length === 0 ? (
        <p className="text-white/40 text-xs italic py-3">Sin fiestas en tu perfil de afiliado (o el token de FourVenues no está configurado).</p>
      ) : (
        <div className="space-y-4">
          {pending.length > 0 && (
            <div data-testid="affiliate-pending">
              <p className="text-orange-300 text-[11px] font-bold uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5" /> Pendientes de añadir ({pending.length})
              </p>
              <p className="text-white/40 text-[10px] mb-2">Sitios de tu slug que aún NO están en la app. Pídelos para que se scrapeen.</p>
              <div className="space-y-1.5">
                {pending.map((v, i) => VenueRow(v, i, true))}
              </div>
            </div>
          )}
          {inApp.length > 0 && (
            <div data-testid="affiliate-inapp">
              <p className="text-emerald-300 text-[11px] font-bold uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Ya en la app ({inApp.length})
              </p>
              <div className="space-y-1.5">
                {inApp.map((v, i) => VenueRow(v, i, false))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
