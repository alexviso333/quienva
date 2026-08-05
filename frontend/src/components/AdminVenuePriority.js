import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { ListOrdered, ArrowUp, ArrowDown, Save, Loader2, Star } from "lucide-react";
import { toast } from "sonner";

export default function AdminVenuePriority() {
  const qc = useQueryClient();
  const { data: venues = [], isLoading } = useQuery({
    queryKey: ["admin-venues"],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 20_000,
  });

  // Local, reorderable copy sorted by importance (venue.order asc). The saved
  // priority is simply the array position (sent to /admin/venues/reorder).
  const [list, setList] = useState([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!dirty) {
      const sorted = [...venues].sort(
        (a, b) => (a.order ?? 9999) - (b.order ?? 9999) || (a.name || "").localeCompare(b.name || "")
      );
      setList(sorted);
    }
  }, [venues, dirty]);

  const move = (idx, dir) => {
    setList((cur) => {
      const j = idx + dir;
      if (j < 0 || j >= cur.length) return cur;
      const next = [...cur];
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
    setDirty(true);
  };

  const save = useMutation({
    mutationFn: async () =>
      (await api.put("/admin/venues/reorder", { venue_ids: list.map((v) => v.id) })).data,
    onSuccess: () => {
      toast.success("Orden guardado");
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["admin-venues"] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  return (
    <div className="px-4 mt-6" data-testid="admin-venue-priority">
      <div className="flex items-center gap-2 mb-2">
        <ListOrdered className="w-4 h-4 text-amber-300" />
        <h2 className="font-display text-base font-bold text-white flex-1">Prioridad de discotecas</h2>
        <span className="text-white/40 text-[11px]">{list.length}</span>
      </div>
      <p className="text-white/40 text-[11px] mb-3">
        Ordena los locales por importancia (arriba = sale primero en el feed). Tus discotecas con tu
        link salen siempre las primeras, pase lo que pase en esta lista.
      </p>

      {isLoading && (
        <div className="py-6 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-white/50" />
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        {list.map((v, i) => (
          <div
            key={v.id}
            data-testid={`priority-row-${v.id}`}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-2"
          >
            <span className="w-6 text-center text-white/40 text-xs font-bold">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-white text-sm font-semibold truncate">{v.name}</span>
                {v.has_affiliate && <Star className="w-3 h-3 text-lime-400 shrink-0" fill="currentColor" />}
              </div>
              <span className="text-white/40 text-[11px] truncate">{v.zone}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <button
                data-testid={`priority-up-${v.id}`}
                onClick={() => move(i, -1)}
                disabled={i === 0}
                aria-label="Subir prioridad"
                className="w-7 h-6 rounded-md bg-white/5 border border-white/10 text-white/70 flex items-center justify-center active:scale-90 disabled:opacity-25"
              >
                <ArrowUp className="w-3.5 h-3.5" />
              </button>
              <button
                data-testid={`priority-down-${v.id}`}
                onClick={() => move(i, 1)}
                disabled={i === list.length - 1}
                aria-label="Bajar prioridad"
                className="w-7 h-6 rounded-md bg-white/5 border border-white/10 text-white/70 flex items-center justify-center active:scale-90 disabled:opacity-25"
              >
                <ArrowDown className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {dirty && (
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          data-testid="priority-save"
          className="mt-3 w-full h-11 rounded-2xl bg-qv-primary text-black font-bold text-sm flex items-center justify-center gap-1.5 active:scale-95 disabled:opacity-50"
        >
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Guardar orden
        </button>
      )}
    </div>
  );
}
