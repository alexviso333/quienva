import { useState } from "react";
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
 * Permite reasignar manualmente la ciudad de cada sitio (cuando la detección
 * automática falla) o mandarlo a "Pendiente de añadir".
 */
export default function AdminAffiliatePanel() {
  const qc = useQueryClient();
  const [busyKey, setBusyKey] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["admin-affiliate-status"],
    queryFn: async () => (await api.get("/admin/affiliate-status")).data,
    staleTime: 60_000,
  });

  const { data: citiesData } = useQuery({
    queryKey: ["cities"],
    queryFn: async () => (await api.get("/cities")).data,
    staleTime: 60 * 60_000,
  });
  const cities = citiesData?.cities || [];
  const pendingCity = citiesData?.pending_city || "Pendiente";

  const refresh = useMutation({
    mutationFn: async () => (await api.post("/admin/affiliate-refresh")).data,
    onSuccess: () => {
      toast.success("Afiliado actualizado");
      qc.invalidateQueries({ queryKey: ["admin-affiliate-status"] });
    },
    onError: () => toast.error("Error al actualizar"),
  });

  const setCity = useMutation({
    mutationFn: async ({ slug, venue, city }) => (await api.post("/admin/affiliate/set-city", { slug, venue, city })).data,
    onSuccess: (d) => {
      const where = d.city === pendingCity ? "Pendientes de añadir" : d.city;
      toast.success(`Movido a ${where}${d.events_updated ? ` · ${d.events_updated} fiestas` : ""} ✅`);
      qc.invalidateQueries({ queryKey: ["admin-affiliate-status"] });
      qc.invalidateQueries({ queryKey: ["admin-scrapers"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      setBusyKey("");
    },
    onError: (e) => { toast.error(e.response?.data?.detail || "No se pudo cambiar la ciudad"); setBusyKey("");},
  });

  const venues = data?.venues || [];
  const inApp = venues.filter((v) => v.in_app);
  const pending = venues.filter((v) => !v.in_app);

  const rowKey = (v, i, pendingRow) => `${pendingRow ? "p" : "a"}-${v.slug || v.key || v.venue}-${i}`;

  const renderVenueRow = (v, i, pendingRow) => {
    const gap = !pendingRow && (v.matched || 0) === 0; // in-app club with 0 marked → coverage gap
    const key = rowKey(v, i, pendingRow);
    const isBusy = busyKey === key && setCity.isPending;
    const selectValue = v.override ? v.city : ""; // "" = auto-detectado / sin decidir
    return (
      <div
        key={key}
        className={`p-2 rounded-xl border ${gap ? "bg-red-500/10 border-red-400/40" : "bg-white/[0.03] border-white/5"}`}
        data-testid={`affiliate-venue-${pendingRow ? "pending" : "inapp"}-${i}`}
      >
        <div className="flex items-center gap-2.5">
          <span className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${pendingRow ? "bg-orange-400/15 text-orange-300" : "bg-emerald-400/15 text-emerald-300"}`}>
            {pendingRow ? <MapPin className="w-3.5 h-3.5" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-white text-xs font-semibold truncate">{v.venue}</p>
            <p className="text-white/40 text-[10px] truncate">
              {v.city || v.detected_city || "Ciudad desconocida"}
              {v.override ? " · manual" : v.detected_city ? " · auto" : ""}
            </p>
          </div>
          {pendingRow ? (
            <span className="text-white/50 text-[10px] font-bold shrink-0 bg-white/5 rounded-full px-2 py-0.5">{v.events} {v.events === 1 ? "fiesta" : "fiestas"}</span>
          ) : (
            <span
              className={`text-[10px] font-bold shrink-0 rounded-full px-2 py-0.5 ${gap ? "bg-red-400/20 text-red-300" : "bg-emerald-400/15 text-emerald-300"}`}
              title="Fiestas marcadas en la app / fiestas que llevas por tu link"
            >
              {v.matched ?? 0}/{v.events} marcadas
            </span>
          )}
        </div>
        {/* City reassignment control */}
        <div className="flex items-center gap-2 mt-2">
          <span className="text-white/40 text-[10px] font-bold uppercase tracking-wide shrink-0">Ciudad</span>
          <select
            data-testid={`affiliate-setcity-${pendingRow ? "pending" : "inapp"}-${i}`}
            value={selectValue}
            disabled={isBusy}
            onChange={(e) => {
              const city = e.target.value;
              if (!city) return;
              setBusyKey(key);
              setCity.mutate({ slug: v.slug || "", venue: v.venue || "", city });
            }}
            className="flex-1 h-8 rounded-lg bg-white/5 border border-white/15 text-white text-[11px] px-2 appearance-none disabled:opacity-50"
          >
            <option value="" className="bg-[#121215]">{pendingRow ? "Elegir ciudad…" : "Cambiar ciudad…"}</option>
            {cities.map((c) => (
              <option key={c.id} value={c.id} className="bg-[#121215]">{c.emoji ? `${c.emoji} ` : ""}{c.label}</option>
            ))}
            <option value={pendingCity} className="bg-[#121215]">⏳ Pendiente de añadir</option>
          </select>
          {isBusy && <Loader2 className="w-4 h-4 animate-spin text-white/60 shrink-0" />}
        </div>
      </div>
    );
  };

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
          Slug <span className="text-qv-secondary font-semibold">{data.slug}</span> · {data.mine_count} fiestas tuyas · {typeof data.matched_count === "number" ? `${data.matched_count} marcadas · ` : ""}{venues.length} locales · act. {whenText(data.updated_at)}
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
              <p className="text-white/40 text-[10px] mb-2">Sitios de tu slug que aún NO están en la app. Elige su ciudad para añadirlos (si no se detectó bien).</p>
              <div className="space-y-1.5">
                {pending.map((v, i) => renderVenueRow(v, i, true))}
              </div>
            </div>
          )}
          {inApp.length > 0 && (
            <div data-testid="affiliate-inapp">
              <p className="text-emerald-300 text-[11px] font-bold uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Ya en la app ({inApp.length})
              </p>
              <p className="text-white/40 text-[10px] mb-2">Puedes cambiarlos a otra ciudad o mandarlos a "Pendiente de añadir".</p>
              <div className="space-y-1.5">
                {inApp.map((v, i) => renderVenueRow(v, i, false))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
