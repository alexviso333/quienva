import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Building2, Plus, Trash2, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

const DAYS = ["L", "M", "X", "J", "V", "S", "D"];
const TYPES = ["discoteca", "pub", "beach_club", "promotor"];

const EMPTY = {
  name: "", zone: "Palma", city: "Palma de Mallorca", type: "discoteca",
  scraper_slug: "", free_entry: false, open_days: [], instagram: "", address: "",
  buy_url: "", open_time: "", close_time: "",
  image_url: "", description: "", active: true, order: 100,
};

function DayPicker({ days, onToggle }) {
  return (
    <div className="flex gap-1">
      {DAYS.map((d, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onToggle(i)}
          className={`w-6 h-6 rounded-md text-[11px] font-bold ${days.includes(i) ? "bg-qv-primary text-black" : "bg-white/5 text-white/40"}`}
        >
          {d}
        </button>
      ))}
    </div>
  );
}

function Row({ v }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState(v);
  const inv = () => qc.invalidateQueries({ queryKey: ["admin-venues"] });
  const save = useMutation({
    mutationFn: async () => (await api.put(`/admin/venues/${v.id}`, edit)).data,
    onSuccess: () => { toast.success("Guardado"); inv(); },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });
  const del = useMutation({
    mutationFn: async () => (await api.delete(`/admin/venues/${v.id}`)).data,
    onSuccess: () => { toast.success("Eliminado"); inv(); },
  });
  const toggleDay = (i) =>
    setEdit((e) => ({ ...e, open_days: e.open_days.includes(i) ? e.open_days.filter((x) => x !== i) : [...e.open_days, i].sort() }));

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-2.5 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <input
          value={edit.name}
          onChange={(e) => setEdit({ ...edit, name: e.target.value })}
          className="flex-1 h-8 bg-white/5 border border-white/10 rounded-lg px-2 text-white text-sm"
        />
        <select
          value={edit.type}
          onChange={(e) => setEdit({ ...edit, type: e.target.value })}
          className="h-8 bg-white/5 border border-white/10 rounded-lg px-1 text-white text-xs"
        >
          {TYPES.map((t) => <option key={t} value={t} className="bg-black">{t}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <input
          value={edit.zone}
          onChange={(e) => setEdit({ ...edit, zone: e.target.value })}
          placeholder="Zona"
          className="flex-1 h-8 bg-white/5 border border-white/10 rounded-lg px-2 text-white text-xs"
        />
        <label className="flex items-center gap-1 text-[11px] text-white/70">
          <input type="checkbox" checked={edit.free_entry} onChange={(e) => setEdit({ ...edit, free_entry: e.target.checked })} /> libre
        </label>
        <label className="flex items-center gap-1 text-[11px] text-white/70">
          <input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} /> activo
        </label>
      </div>
      <div className="flex items-center justify-between gap-2">
        <DayPicker days={edit.open_days} onToggle={toggleDay} />
        <div className="flex items-center gap-1">
          <input value={edit.open_time || ""} onChange={(e) => setEdit({ ...edit, open_time: e.target.value })} placeholder="23:00" className="w-14 h-7 bg-white/5 border border-white/10 rounded-lg px-1.5 text-white text-[11px] text-center" />
          <span className="text-white/30 text-[11px]">–</span>
          <input value={edit.close_time || ""} onChange={(e) => setEdit({ ...edit, close_time: e.target.value })} placeholder="06:00" className="w-14 h-7 bg-white/5 border border-white/10 rounded-lg px-1.5 text-white text-[11px] text-center" />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input value={edit.buy_url || ""} onChange={(e) => setEdit({ ...edit, buy_url: e.target.value })} placeholder="Link entradas (web propia)" className="flex-1 h-7 bg-white/5 border border-white/10 rounded-lg px-2 text-white text-[11px]" />
        <div className="flex gap-1.5">
          <button onClick={() => save.mutate()} disabled={save.isPending} className="text-[11px] font-bold text-black bg-qv-primary rounded-lg px-2.5 py-1.5 flex items-center gap-1 active:scale-95">
            {save.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} Guardar
          </button>
          <button onClick={() => { if (window.confirm(`¿Eliminar ${v.name}?`)) del.mutate(); }} className="text-[11px] text-white/60 bg-white/5 border border-white/10 rounded-lg px-2 py-1.5">
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminVenuesPanel() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [nv, setNv] = useState(EMPTY);
  const { data: venues = [], isLoading } = useQuery({
    queryKey: ["admin-venues"],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 20_000,
  });
  const create = useMutation({
    mutationFn: async () => (await api.post("/admin/venues", nv)).data,
    onSuccess: () => { toast.success("Local añadido"); setAdding(false); setNv(EMPTY); qc.invalidateQueries({ queryKey: ["admin-venues"] }); },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });
  const toggleNvDay = (i) =>
    setNv((e) => ({ ...e, open_days: e.open_days.includes(i) ? e.open_days.filter((x) => x !== i) : [...e.open_days, i].sort() }));

  return (
    <div className="px-4 mt-6" data-testid="admin-venues-panel">
      <div className="flex items-center gap-2 mb-2">
        <Building2 className="w-4 h-4 text-fuchsia-300" />
        <h2 className="font-display text-base font-bold text-white flex-1">Directorio de locales</h2>
        <span className="text-white/40 text-[11px]">{venues.length}</span>
      </div>
      <p className="text-white/40 text-[11px] mb-3">Edita días de apertura, tipo o entrada libre. Añade locales sin venta online (Banana, Milano, pubs...).</p>

      {isLoading && <div className="py-6 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-white/50" /></div>}

      <div className="flex flex-col gap-2">
        {venues.map((v) => <Row key={v.id} v={v} />)}
      </div>

      {!adding ? (
        <button onClick={() => setAdding(true)} className="mt-3 w-full h-11 rounded-2xl border border-dashed border-white/20 text-white/60 text-sm font-bold flex items-center justify-center gap-1.5 active:scale-95">
          <Plus className="w-4 h-4" /> Añadir local
        </button>
      ) : (
        <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3 flex flex-col gap-2">
          <input placeholder="Nombre" value={nv.name} onChange={(e) => setNv({ ...nv, name: e.target.value })} className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm" />
          <div className="flex gap-2">
            <input placeholder="Zona (ej. Alcúdia)" value={nv.zone} onChange={(e) => setNv({ ...nv, zone: e.target.value })} className="flex-1 h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm" />
            <select value={nv.type} onChange={(e) => setNv({ ...nv, type: e.target.value })} className="h-10 bg-white/5 border border-white/10 rounded-lg px-2 text-white text-sm">
              {TYPES.map((t) => <option key={t} value={t} className="bg-black">{t}</option>)}
            </select>
          </div>
          <input placeholder="Instagram (sin @)" value={nv.instagram} onChange={(e) => setNv({ ...nv, instagram: e.target.value })} className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm" />
          <input placeholder="Dirección" value={nv.address} onChange={(e) => setNv({ ...nv, address: e.target.value })} className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm" />
          <input placeholder="Link entradas (opcional, web propia)" value={nv.buy_url} onChange={(e) => setNv({ ...nv, buy_url: e.target.value })} className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm" />
          <div className="flex items-center gap-2">
            <span className="text-white/50 text-xs">Horario</span>
            <input placeholder="23:00" value={nv.open_time} onChange={(e) => setNv({ ...nv, open_time: e.target.value })} className="w-20 h-10 bg-white/5 border border-white/10 rounded-lg px-2 text-white text-sm text-center" />
            <span className="text-white/30">–</span>
            <input placeholder="06:00" value={nv.close_time} onChange={(e) => setNv({ ...nv, close_time: e.target.value })} className="w-20 h-10 bg-white/5 border border-white/10 rounded-lg px-2 text-white text-sm text-center" />
          </div>
          <div className="flex items-center justify-between">
            <DayPicker days={nv.open_days} onToggle={toggleNvDay} />
            <label className="flex items-center gap-1 text-[11px] text-white/70">
              <input type="checkbox" checked={nv.free_entry} onChange={(e) => setNv({ ...nv, free_entry: e.target.checked })} /> entrada libre
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={() => create.mutate()} disabled={!nv.name || create.isPending} className="flex-1 h-10 rounded-lg bg-qv-primary text-black font-bold text-sm active:scale-95 disabled:opacity-50">
              {create.isPending ? "Guardando..." : "Añadir"}
            </button>
            <button onClick={() => setAdding(false)} className="px-4 h-10 rounded-lg bg-white/10 text-white text-sm">Cancelar</button>
          </div>
        </div>
      )}
    </div>
  );
}
