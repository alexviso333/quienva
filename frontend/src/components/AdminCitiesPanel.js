import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { MapPin, Plus, Trash2, Loader2, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

/**
 * Admin panel to manage the app's cities dynamically (no app update needed).
 * Cities live in the `app_cities` collection; the native app reads the live
 * list from /api/cities. Adding "Sevilla" here makes it appear instantly.
 * Removing a city sends its parties + scraped venues to "Pendiente" (reversible).
 */
export default function AdminCitiesPanel() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [nc, setNc] = useState({ label: "", emoji: "" });

  const { data, isLoading } = useQuery({
    queryKey: ["admin-cities"],
    queryFn: async () => (await api.get("/admin/cities")).data,
    staleTime: 15_000,
  });
  const cities = data?.cities || [];
  const pendingEvents = data?.pending_events || 0;

  const inv = () => {
    qc.invalidateQueries({ queryKey: ["admin-cities"] });
    qc.invalidateQueries({ queryKey: ["cities"] });
  };

  const create = useMutation({
    mutationFn: async () => (await api.post("/admin/cities", nc)).data,
    onSuccess: () => {
      toast.success("Ciudad añadida");
      setAdding(false);
      setNc({ label: "", emoji: "" });
      inv();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  const toggle = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/cities/${encodeURIComponent(id)}/toggle`)).data,
    onSuccess: (d) => { toast.success(d.enabled ? "Ciudad visible" : "Ciudad oculta"); inv(); },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  const remove = useMutation({
    mutationFn: async (id) => (await api.delete(`/admin/cities/${encodeURIComponent(id)}`)).data,
    onSuccess: (d) => {
      toast.success(`Ciudad eliminada · ${d.events_moved || 0} fiestas y ${d.venues_moved || 0} locales pasaron a Pendiente`);
      inv();
      qc.invalidateQueries({ queryKey: ["admin-scrapers"] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  return (
    <div className="px-4 mt-6" data-testid="admin-cities-panel">
      <div className="flex items-center gap-2 mb-2">
        <MapPin className="w-4 h-4 text-sky-300" />
        <h2 className="font-display text-base font-bold text-white flex-1">Ciudades de la app</h2>
        <span className="text-white/40 text-[11px]">{cities.length}</span>
      </div>
      <p className="text-white/40 text-[11px] mb-3 leading-snug">
        Añade o quita ciudades sin actualizar la app: la app lee la lista en vivo. Al eliminar una
        ciudad, sus fiestas y discotecas pasan a <span className="text-amber-300">Pendiente</span> (reversible).
      </p>

      {pendingEvents > 0 && (
        <div className="rounded-xl border border-amber-400/25 bg-amber-400/5 px-3 py-2 mb-3 text-[11px] text-amber-200">
          {pendingEvents} fiestas próximas están en <b>Pendiente</b> (sin ciudad). Asígnalas desde el scraper de discotecas.
        </div>
      )}

      {isLoading && <div className="py-6 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-white/50" /></div>}

      <div className="flex flex-col gap-2">
        {cities.map((c) => (
          <div
            key={c.id}
            className={`rounded-xl border p-3 flex items-center gap-3 ${c.enabled === false ? "border-white/10 bg-white/[0.02] opacity-60" : "border-white/10 bg-white/[0.04]"}`}
            data-testid={`admin-city-${c.id}`}
          >
            <span className="text-xl leading-none">{c.emoji || "📍"}</span>
            <div className="flex-1 min-w-0">
              <p className="font-bold text-sm text-white truncate">{c.label || c.id}</p>
              <p className="text-white/40 text-[11px]">
                {c.events_upcoming || 0} fiestas próximas
                {c.enabled === false && <span className="text-white/30"> · oculta</span>}
              </p>
            </div>
            <button
              onClick={() => toggle.mutate(c.id)}
              title={c.enabled === false ? "Mostrar" : "Ocultar"}
              className="text-white/70 bg-white/5 border border-white/10 rounded-lg p-2 active:scale-95"
              data-testid={`admin-city-toggle-${c.id}`}
            >
              {c.enabled === false ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={() => {
                if (window.confirm(`¿Eliminar ${c.label || c.id}? Sus fiestas y discotecas pasarán a Pendiente.`)) remove.mutate(c.id);
              }}
              className="text-white/60 bg-white/5 border border-white/10 rounded-lg p-2 active:scale-95"
              data-testid={`admin-city-delete-${c.id}`}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {!adding ? (
        <button
          onClick={() => setAdding(true)}
          className="mt-3 w-full h-11 rounded-2xl border border-dashed border-white/20 text-white/60 text-sm font-bold flex items-center justify-center gap-1.5 active:scale-95 hover:text-white hover:border-white/40"
          data-testid="admin-city-add-btn"
        >
          <Plus className="w-4 h-4" /> Añadir ciudad
        </button>
      ) : (
        <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3 flex flex-col gap-2">
          <div className="flex gap-2">
            <input
              placeholder="Emoji"
              value={nc.emoji}
              onChange={(e) => setNc({ ...nc, emoji: e.target.value })}
              className="w-16 h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm text-center placeholder:text-white/40"
              data-testid="admin-city-emoji"
            />
            <input
              placeholder="Nombre de la ciudad (ej. Sevilla)"
              value={nc.label}
              onChange={(e) => setNc({ ...nc, label: e.target.value })}
              className="flex-1 h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm placeholder:text-white/40"
              data-testid="admin-city-label"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => create.mutate()}
              disabled={!nc.label.trim() || create.isPending}
              className="flex-1 h-10 rounded-lg bg-qv-primary text-black font-bold text-sm active:scale-95 disabled:opacity-50"
              data-testid="admin-city-save"
            >
              {create.isPending ? "Guardando..." : "Añadir"}
            </button>
            <button onClick={() => { setAdding(false); setNc({ label: "", emoji: "" }); }} className="px-4 h-10 rounded-lg bg-white/10 text-white text-sm">
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
