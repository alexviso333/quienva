import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl, formatApiErrorDetail } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, ArrowLeft, ImageUp, Loader2, Ticket, ExternalLink } from "lucide-react";
import { toast } from "sonner";

const EMPTY = {
  name: "", venue: "", address: "", date: "", time: "", image_url: "",
  genre: "", city: "Palma de Mallorca", has_commission: false,
  commission_url: "", more_info_url: "",
};

function EventForm({ initial, onSaved }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(initial || EMPTY);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/admin/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm((f) => ({ ...f, image_url: data.image_url }));
      toast.success("Imagen subida");
    } catch {
      toast.error("Error al subir imagen");
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    if (!form.name || !form.venue || !form.date) {
      toast.error("Nombre, local y fecha son obligatorios");
      return;
    }
    setSaving(true);
    try {
      if (initial?.id) await api.put(`/admin/events/${initial.id}`, form);
      else await api.post("/admin/events", form);
      qc.invalidateQueries({ queryKey: ["admin-events"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      toast.success("Guardado");
      onSaved();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const inputCls = "h-11 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40";

  return (
    <div className="flex flex-col gap-3">
      <div
        onClick={() => document.getElementById("admin-img-input").click()}
        className="relative h-40 rounded-2xl overflow-hidden border border-white/15 bg-white/5 flex items-center justify-center cursor-pointer"
        data-testid="admin-image-drop"
      >
        {form.image_url ? (
          <img src={mediaUrl(form.image_url)} alt="preview" className="w-full h-full object-cover" />
        ) : (
          <div className="text-white/40 flex flex-col items-center gap-2 text-sm">
            {uploading ? <Loader2 className="w-6 h-6 animate-spin" /> : <ImageUp className="w-6 h-6" />}
            Subir imagen
          </div>
        )}
        <input id="admin-img-input" type="file" accept="image/*" hidden onChange={upload} data-testid="admin-image-input" />
      </div>
      <Input data-testid="admin-name" placeholder="Nombre del evento" value={form.name} onChange={set("name")} className={inputCls} />
      <div className="grid grid-cols-2 gap-3">
        <Input data-testid="admin-venue" placeholder="Local" value={form.venue} onChange={set("venue")} className={inputCls} />
        <Input data-testid="admin-genre" placeholder="Género / ambiente" value={form.genre} onChange={set("genre")} className={inputCls} />
      </div>
      <Input data-testid="admin-address" placeholder="Dirección" value={form.address} onChange={set("address")} className={inputCls} />
      <div className="grid grid-cols-2 gap-3">
        <Input data-testid="admin-date" type="date" value={form.date} onChange={set("date")} className={inputCls} />
        <Input data-testid="admin-time" type="time" value={form.time} onChange={set("time")} className={inputCls} />
      </div>

      <div className="flex items-center justify-between bg-white/5 border border-white/15 rounded-xl px-4 h-12">
        <span className="text-sm text-white/80">¿Tiene enlace de comisión / RRPP?</span>
        <Switch
          data-testid="admin-has-commission"
          checked={form.has_commission}
          onCheckedChange={(v) => setForm({ ...form, has_commission: v })}
        />
      </div>

      {form.has_commission ? (
        <Input data-testid="admin-commission-url" placeholder="URL de la entrada (comisión)" value={form.commission_url} onChange={set("commission_url")} className={inputCls} />
      ) : (
        <Input data-testid="admin-info-url" placeholder="URL de más info (web / Instagram)" value={form.more_info_url} onChange={set("more_info_url")} className={inputCls} />
      )}

      <DialogFooter>
        <button
          data-testid="admin-save-event"
          onClick={submit}
          disabled={saving}
          className="h-12 w-full rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60"
        >
          {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : "Guardar evento"}
        </button>
      </DialogFooter>
    </div>
  );
}

export default function Admin() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [openNew, setOpenNew] = useState(false);
  const [editing, setEditing] = useState(null);

  const { data: events = [], isLoading } = useQuery({
    queryKey: ["admin-events"],
    queryFn: async () => (await api.get("/admin/events")).data,
  });

  const del = useMutation({
    mutationFn: async (id) => (await api.delete(`/admin/events/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-events"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      toast.success("Evento borrado");
    },
  });

  return (
    <div className="min-h-screen qv-app-bg">
      <div className="max-w-md mx-auto min-h-screen pb-10">
        <header className="px-5 pt-8 pb-4 flex items-center gap-3">
          <button data-testid="admin-back" onClick={() => navigate("/feed")} className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="font-display text-2xl font-black tracking-tighter">Panel admin</h1>
            <p className="text-white/40 text-xs">{events.length} eventos</p>
          </div>
        </header>

        <div className="px-5">
          <Dialog open={openNew} onOpenChange={setOpenNew}>
            <DialogTrigger asChild>
              <button
                data-testid="admin-new-event"
                className="h-12 w-full rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform mb-4"
              >
                <Plus className="w-5 h-5" /> Nuevo evento
              </button>
            </DialogTrigger>
            <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="font-display">Nuevo evento</DialogTitle>
              </DialogHeader>
              <EventForm onSaved={() => setOpenNew(false)} />
            </DialogContent>
          </Dialog>
        </div>

        <div className="px-5 flex flex-col gap-3">
          {isLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-qv-primary" /></div>
          ) : (
            events.map((ev) => (
              <div key={ev.id} className="flex gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`admin-event-${ev.id}`}>
                {ev.image_url && (
                  <img src={mediaUrl(ev.image_url)} alt={ev.name} className="w-16 h-16 rounded-xl object-cover shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{ev.name}</p>
                  <p className="text-white/40 text-sm truncate">{ev.venue} · {ev.date}</p>
                  <span className="inline-flex items-center gap-1 text-xs mt-1 text-white/50">
                    {ev.has_commission ? <><Ticket className="w-3 h-3" /> Comisión</> : <><ExternalLink className="w-3 h-3" /> Info</>}
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  <button data-testid={`admin-edit-${ev.id}`} onClick={() => setEditing(ev)} className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center">
                    <Pencil className="w-4 h-4 text-white/80" />
                  </button>
                  <button data-testid={`admin-delete-${ev.id}`} onClick={() => del.mutate(ev.id)} className="w-9 h-9 rounded-full bg-qv-primary/20 flex items-center justify-center">
                    <Trash2 className="w-4 h-4 text-qv-primary" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
          <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="font-display">Editar evento</DialogTitle>
            </DialogHeader>
            {editing && <EventForm initial={editing} onSaved={() => setEditing(null)} />}
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
