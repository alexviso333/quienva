import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Moon, Shuffle, Zap, Pause, Play, Clock, CheckCircle2, Loader2, X } from "lucide-react";
import { toast } from "sonner";

/**
 * Admin control panel for "El Momento" (BeReal-style photo prompt).
 * Shows tonight's events, lets admin:
 *  - see planned time / status
 *  - randomize (1 or all) between 01:00-05:59
 *  - set a specific time
 *  - fire manually right now
 *  - pause/unpause per event
 */
export default function AdminMomentPanel() {
  const qc = useQueryClient();
  const [editingId, setEditingId] = useState(null);
  const [hour, setHour] = useState(3);
  const [minute, setMinute] = useState(0);

  const { data: events = [], isLoading } = useQuery({
    queryKey: ["admin-moments"],
    queryFn: async () => (await api.get("/admin/moments")).data,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-moments"] });

  const randomizeAll = useMutation({
    mutationFn: async () => (await api.post("/admin/moments/randomize-all")).data,
    onSuccess: (d) => {
      toast.success(`${d.updated} eventos randomizados`);
      invalidate();
    },
    onError: () => toast.error("No se pudo randomizar"),
  });

  const randomizeOne = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/moments/${id}/randomize`)).data,
    onSuccess: () => {
      toast.success("Hora nueva asignada");
      invalidate();
    },
  });

  const setTime = useMutation({
    mutationFn: async ({ id, hour, minute }) =>
      (await api.put(`/admin/moments/${id}`, { hour, minute })).data,
    onSuccess: () => {
      toast.success("Hora actualizada");
      setEditingId(null);
      invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  const cancelOne = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/moments/${id}/cancel`)).data,
    onSuccess: () => {
      toast.success("Momento pausado — no saltará");
      invalidate();
    },
  });

  const uncancelOne = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/moments/${id}/uncancel`)).data,
    onSuccess: () => {
      toast.success("Momento reactivado");
      invalidate();
    },
  });

  const fireNow = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/events/${id}/moment/trigger`)).data,
    onSuccess: (d) => {
      toast.success(`⚡ ¡Disparado! ${d.notified} usuarios notificados`);
      invalidate();
    },
    onError: () => toast.error("Error al disparar"),
  });

  const formatPlanned = (iso) => {
    if (!iso) return "sin hora";
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString("es-ES", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Madrid",
      });
    } catch {
      return "—";
    }
  };

  const formatDate = (isoDate) => {
    try {
      const d = new Date(isoDate + "T00:00:00");
      return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
    } catch {
      return isoDate;
    }
  };

  const startEdit = (ev) => {
    setEditingId(ev.id);
    if (ev.planned_moment_at) {
      const d = new Date(ev.planned_moment_at);
      // Extract Madrid-time hour/minute
      const parts = new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Europe/Madrid",
      }).formatToParts(d);
      const h = parseInt(parts.find((p) => p.type === "hour")?.value || "3", 10);
      const m = parseInt(parts.find((p) => p.type === "minute")?.value || "0", 10);
      setHour(h >= 1 && h <= 5 ? h : 3);
      setMinute(m);
    } else {
      setHour(3);
      setMinute(0);
    }
  };

  return (
    <div className="px-4 mt-6" data-testid="admin-moment-panel">
      <div className="flex items-center gap-2 mb-2">
        <Moon className="w-4 h-4 text-fuchsia-300" />
        <h2 className="font-display text-base font-bold text-white flex-1">
          El Momento · esta noche
        </h2>
        <button
          onClick={() => randomizeAll.mutate()}
          disabled={randomizeAll.isPending || events.length === 0}
          className="text-xs font-bold text-black bg-fuchsia-300 rounded-full px-3 py-1.5 flex items-center gap-1 active:scale-95 disabled:opacity-50"
          data-testid="moment-randomize-all"
        >
          <Shuffle className="w-3.5 h-3.5" /> Randomizar todos
        </button>
      </div>
      <p className="text-white/40 text-[11px] mb-3 leading-snug">
        Cada noche, entre las 01:00 y las 05:59, saltará una foto tipo BeReal a los que van.
        Aquí controlas a qué hora exacta en cada fiesta.
      </p>

      {isLoading && (
        <div className="py-10 flex justify-center">
          <Loader2 className="w-5 h-5 text-white/50 animate-spin" />
        </div>
      )}

      {!isLoading && events.length === 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-center text-white/50 text-sm">
          No hay eventos programados para esta noche.
        </div>
      )}

      <div className="flex flex-col gap-2">
        {events.map((ev) => {
          const isEditing = editingId === ev.id;
          const cancelled = ev.moment_cancelled;
          const fired = ev.has_fired;
          const noVoys = ev.voy_count === 0;
          return (
            <div
              key={ev.id}
              className={`rounded-2xl border p-3 ${
                fired
                  ? "border-emerald-400/30 bg-emerald-400/5"
                  : cancelled
                  ? "border-white/10 bg-white/[0.02] opacity-60"
                  : "border-white/10 bg-white/[0.04]"
              }`}
              data-testid={`moment-event-${ev.id}`}
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-sm text-white truncate">{ev.name}</p>
                  <p className="text-white/40 text-[11px] truncate">
                    {ev.venue} · {formatDate(ev.date)}
                    {ev.time ? ` · ${ev.time}h` : ""}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold flex items-center gap-1 ${
                      fired
                        ? "bg-emerald-400/20 text-emerald-300"
                        : cancelled
                        ? "bg-white/10 text-white/50"
                        : "bg-fuchsia-400/20 text-fuchsia-200"
                    }`}>
                      <Clock className="w-3 h-3" />
                      {fired
                        ? `Disparado ${formatPlanned(ev.fired_at)}`
                        : cancelled
                        ? "Pausado"
                        : formatPlanned(ev.planned_moment_at)}
                    </span>
                    <span className="text-[10px] text-white/40">
                      {ev.voy_count} van · {ev.captures_count} fotos
                    </span>
                  </div>
                </div>
              </div>

              {isEditing ? (
                <div className="mt-3 flex items-center gap-2">
                  <select
                    value={hour}
                    onChange={(e) => setHour(parseInt(e.target.value, 10))}
                    className="bg-white/10 border border-white/10 rounded-lg px-2 py-1.5 text-white text-sm"
                    data-testid={`moment-hour-${ev.id}`}
                  >
                    {[1, 2, 3, 4, 5].map((h) => (
                      <option key={h} value={h} className="bg-black">
                        {String(h).padStart(2, "0")}
                      </option>
                    ))}
                  </select>
                  <span className="text-white/60 text-sm">:</span>
                  <select
                    value={minute}
                    onChange={(e) => setMinute(parseInt(e.target.value, 10))}
                    className="bg-white/10 border border-white/10 rounded-lg px-2 py-1.5 text-white text-sm"
                    data-testid={`moment-minute-${ev.id}`}
                  >
                    {[0, 10, 15, 20, 30, 40, 45, 50].map((m) => (
                      <option key={m} value={m} className="bg-black">
                        {String(m).padStart(2, "0")}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => setTime.mutate({ id: ev.id, hour, minute })}
                    disabled={setTime.isPending}
                    className="ml-auto text-xs font-bold bg-qv-primary text-black rounded-full px-3 py-1.5 active:scale-95 disabled:opacity-50"
                    data-testid={`moment-save-${ev.id}`}
                  >
                    Guardar
                  </button>
                  <button
                    onClick={() => setEditingId(null)}
                    className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center"
                    aria-label="Cancelar"
                  >
                    <X className="w-4 h-4 text-white/70" />
                  </button>
                </div>
              ) : (
                <div className="mt-3 grid grid-cols-4 gap-1.5">
                  <button
                    onClick={() => startEdit(ev)}
                    disabled={fired}
                    className="text-[10px] font-bold text-white bg-white/10 rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95 disabled:opacity-40"
                    data-testid={`moment-edit-${ev.id}`}
                  >
                    <Clock className="w-3 h-3" /> Cambiar
                  </button>
                  <button
                    onClick={() => randomizeOne.mutate(ev.id)}
                    disabled={fired || randomizeOne.isPending}
                    className="text-[10px] font-bold text-white bg-white/10 rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95 disabled:opacity-40"
                    data-testid={`moment-randomize-${ev.id}`}
                  >
                    <Shuffle className="w-3 h-3" /> Random
                  </button>
                  <button
                    onClick={() => fireNow.mutate(ev.id)}
                    disabled={fireNow.isPending || noVoys}
                    className="text-[10px] font-bold text-black bg-qv-secondary rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95 disabled:opacity-40"
                    data-testid={`moment-fire-${ev.id}`}
                  >
                    <Zap className="w-3 h-3" /> AHORA
                  </button>
                  {cancelled ? (
                    <button
                      onClick={() => uncancelOne.mutate(ev.id)}
                      disabled={fired}
                      className="text-[10px] font-bold text-black bg-emerald-300 rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95 disabled:opacity-40"
                      data-testid={`moment-uncancel-${ev.id}`}
                    >
                      <Play className="w-3 h-3" /> Activar
                    </button>
                  ) : (
                    <button
                      onClick={() => cancelOne.mutate(ev.id)}
                      disabled={fired}
                      className="text-[10px] font-bold text-white bg-white/10 rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95 disabled:opacity-40"
                      data-testid={`moment-cancel-${ev.id}`}
                    >
                      <Pause className="w-3 h-3" /> Pausar
                    </button>
                  )}
                </div>
              )}

              {noVoys && !fired && !isEditing && (
                <p className="text-[10px] text-white/40 mt-2 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />
                  Nadie va a esta fiesta. No se disparará aunque llegue la hora.
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
