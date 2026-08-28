import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl, mediaThumb, formatApiErrorDetail } from "@/lib/api";
import AdminEventStats from "@/components/AdminEventStats";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, ArrowLeft, ImageUp, Loader2, Ticket, ExternalLink, Link as LinkIcon, Wand2, Zap, Tag, X, BellRing, BarChart3, CalendarDays, History } from "lucide-react";
import { toast } from "sonner";

const CITIES = [
  { value: "Palma de Mallorca", label: "Mallorca" },
  { value: "Ibiza", label: "Ibiza" },
  { value: "Madrid", label: "Madrid" },
  { value: "Barcelona", label: "Barcelona" },
  { value: "Marbella", label: "Marbella" },
];

const EMPTY = {
  name: "", venue: "", address: "", date: "", time: "", image_url: "",
  genre: "", city: "Palma de Mallorca", has_commission: false,
  commission_url: "", more_info_url: "",
  price_tiers: [],
  sale_state: "no_a_la_venta",
  currency: "EUR",
};

const SALE_STATES = [
  { value: "no_a_la_venta", label: "Aún no a la venta", color: "text-white/70" },
  { value: "a_la_venta", label: "A la venta", color: "text-emerald-300" },
  { value: "pocas_entradas", label: "Pocas entradas", color: "text-orange-300" },
  { value: "agotado", label: "Agotado", color: "text-white/40" },
];

function EventForm({ initial, onSaved, cityDefault }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(() => {
    if (!initial) return { ...EMPTY, city: cityDefault || EMPTY.city };
    // Ensure pricing defaults are set on legacy events
    return {
      ...EMPTY,
      ...initial,
      price_tiers: initial.price_tiers || [],
      sale_state: initial.sale_state || "no_a_la_venta",
      currency: initial.currency || "EUR",
    };
  });
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  // When editing: whether to send push notifications for pricing changes.
  const [notifyOnSave, setNotifyOnSave] = useState(true);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const addTier = () => setForm({ ...form, price_tiers: [...form.price_tiers, { name: "", price: 0, sold_out: false }] });
  const removeTier = (i) => setForm({ ...form, price_tiers: form.price_tiers.filter((_, j) => j !== i) });
  const updateTier = (i, patch) => setForm({
    ...form,
    price_tiers: form.price_tiers.map((t, j) => (j === i ? { ...t, ...patch } : t)),
  });

  const importFromUrl = async () => {
    const url = importUrl.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) {
      toast.error("Pega una URL que empiece por http(s)://");
      return;
    }
    setImporting(true);
    try {
      const { data } = await api.post("/admin/import-url", { url });
      setForm((f) => ({
        ...f,
        name: data.name || f.name,
        venue: data.venue || f.venue,
        address: data.address || f.address,
        date: data.date || f.date,
        genre: data.genre || f.genre,
        image_url: data.image_url || f.image_url,
        more_info_url: data.more_info_url || f.more_info_url,
        has_commission: data.has_commission ?? f.has_commission,
        commission_url: data.commission_url || f.commission_url,
      }));
      const bits = [];
      if (data.name) bits.push("nombre");
      if (data.venue) bits.push("local");
      if (data.address) bits.push("dirección");
      if (data.date) bits.push("fecha");
      if (data.genre) bits.push("género");
      if (data.image_url) bits.push("imagen");
      if (bits.length) toast.success(`Importado: ${bits.join(", ")}`);
      else toast.info("URL guardada, rellena el resto a mano");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "No se pudo importar");
    } finally {
      setImporting(false);
    }
  };

  const uploadFile = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      // Preserve extension for the backend; blobs from paste have no name
      const named = file.name ? file : new File([file], `pasted-${Date.now()}.png`, { type: file.type || "image/png" });
      fd.append("file", named);
      const { data } = await api.post("/admin/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm((f) => ({ ...f, image_url: data.image_url }));
      toast.success("Imagen subida");
    } catch {
      toast.error("Error al subir imagen");
    } finally {
      setUploading(false);
    }
  };

  const upload = (e) => uploadFile(e.target.files?.[0]);

  const onPasteImage = async (e) => {
    const items = e.clipboardData?.items || [];
    for (const it of items) {
      if (it.kind === "file" && it.type.startsWith("image/")) {
        e.preventDefault();
        await uploadFile(it.getAsFile());
        return;
      }
    }
  };

  const submit = async () => {
    if (!form.name || !form.venue || !form.date) {
      toast.error("Nombre, local y fecha son obligatorios");
      return;
    }
    setSaving(true);
    try {
      if (initial?.id) {
        // Edit: save basic fields via PUT, then send pricing via dedicated
        // endpoint so notifications fire when relevant (state changes).
        await api.put(`/admin/events/${initial.id}`, form);
        try {
          const { data } = await api.put(`/admin/events/${initial.id}/pricing`, {
            price_tiers: form.price_tiers || [],
            sale_state: form.sale_state || "no_a_la_venta",
            silent: !notifyOnSave,
          });
          if (data?.notifications_sent > 0) {
            toast.success(`Guardado · ${data.notifications_sent} usuarios notificados`);
          } else {
            toast.success("Guardado");
          }
        } catch (e) {
          // Pricing endpoint failed — event still saved, just no notif.
          toast.warning("Guardado (sin notificaciones)");
        }
      } else {
        await api.post("/admin/events", form);
        toast.success("Guardado · notificando ciudad…");
      }
      qc.invalidateQueries({ queryKey: ["admin-events"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
      qc.invalidateQueries({ queryKey: ["top-weekend"] });
      onSaved();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const inputCls = "h-11 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40";

  return (
    <div className="flex flex-col gap-3" onPaste={onPasteImage} data-testid="admin-event-form">
      {!initial?.id && (
        <div className="rounded-2xl border border-qv-secondary/40 bg-qv-secondary/5 p-3 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-qv-secondary text-xs font-bold uppercase tracking-widest">
            <Wand2 className="w-3.5 h-3.5" /> Importar desde URL
          </div>
          <p className="text-white/50 text-xs -mt-1">
            Pega el enlace del evento (Fourvenues, web del local, Instagram…) y rellenamos nombre e imagen.
          </p>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <LinkIcon className="w-4 h-4 text-white/40 absolute left-3 top-1/2 -translate-y-1/2" />
              <Input
                data-testid="admin-import-url"
                placeholder="https://..."
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                className="h-11 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40"
              />
            </div>
            <button
              data-testid="admin-import-btn"
              onClick={importFromUrl}
              disabled={importing || !importUrl.trim()}
              className="h-11 px-4 rounded-xl bg-qv-secondary text-black font-bold text-sm flex items-center justify-center gap-1 active:scale-95 transition-transform disabled:opacity-50"
            >
              {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Importar</>}
            </button>
          </div>
        </div>
      )}

      <div
        onClick={() => document.getElementById("admin-img-input").click()}
        onPaste={onPasteImage}
        tabIndex={0}
        className="relative h-40 rounded-2xl overflow-hidden border border-white/15 bg-white/5 flex items-center justify-center cursor-pointer outline-none focus:border-qv-secondary focus:ring-2 focus:ring-qv-secondary/40"
        data-testid="admin-image-drop"
      >
        {form.image_url ? (
          <img src={mediaUrl(form.image_url)} alt="preview" className="w-full h-full object-cover" />
        ) : (
          <div className="text-white/40 flex flex-col items-center gap-1.5 text-sm">
            {uploading ? <Loader2 className="w-6 h-6 animate-spin" /> : <ImageUp className="w-6 h-6" />}
            <span>Subir imagen</span>
            <span className="text-[11px] text-white/30">o pega desde el portapapeles</span>
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
        <select
          data-testid="admin-city"
          value={form.city}
          onChange={set("city")}
          className={inputCls + " px-3 appearance-none"}
        >
          {CITIES.map((c) => (
            <option key={c.value} value={c.value} className="bg-qv-bg text-white">{c.label}</option>
          ))}
        </select>
        <div />
      </div>
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

      {/* ==== PRECIOS Y ESTADO DE VENTA ==== */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3 flex flex-col gap-3" data-testid="admin-pricing-section">
        <div className="flex items-center gap-2 text-white/90 text-xs font-bold uppercase tracking-widest">
          <Tag className="w-3.5 h-3.5 text-qv-secondary" /> Entradas y precios
        </div>

        <div className="grid grid-cols-2 gap-2">
          <select
            value={form.sale_state}
            onChange={set("sale_state")}
            className="h-11 bg-white/5 border border-white/15 rounded-xl text-white px-3 text-sm"
            data-testid="admin-sale-state"
          >
            {SALE_STATES.map((s) => (
              <option key={s.value} value={s.value} className="bg-black">{s.label}</option>
            ))}
          </select>
          <select
            value={form.currency}
            onChange={set("currency")}
            className="h-11 bg-white/5 border border-white/15 rounded-xl text-white px-3 text-sm"
          >
            <option value="EUR" className="bg-black">€ EUR</option>
            <option value="USD" className="bg-black">$ USD</option>
            <option value="GBP" className="bg-black">£ GBP</option>
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          {form.price_tiers.map((t, i) => (
            <div key={i} className="flex items-center gap-1.5" data-testid={`admin-tier-${i}`}>
              <Input
                placeholder={`Fase ${i + 1} (ej. Early bird)`}
                value={t.name}
                onChange={(e) => updateTier(i, { name: e.target.value })}
                className="h-10 bg-white/5 border-white/15 rounded-lg text-white placeholder:text-white/40 text-sm flex-1"
              />
              <Input
                type="number"
                min="0"
                step="0.5"
                placeholder="€"
                value={t.price}
                onChange={(e) => updateTier(i, { price: parseFloat(e.target.value || "0") })}
                className="h-10 bg-white/5 border-white/15 rounded-lg text-white placeholder:text-white/40 text-sm w-20"
                data-testid={`admin-tier-price-${i}`}
              />
              <label className={`h-10 px-2 rounded-lg border cursor-pointer flex items-center gap-1 text-[10px] font-bold uppercase ${
                t.sold_out ? "bg-white/10 border-white/25 text-white/50" : "bg-emerald-400/10 border-emerald-400/30 text-emerald-300"
              }`}>
                <input
                  type="checkbox"
                  checked={t.sold_out}
                  onChange={(e) => updateTier(i, { sold_out: e.target.checked })}
                  className="w-3 h-3"
                  data-testid={`admin-tier-soldout-${i}`}
                />
                {t.sold_out ? "Agot." : "Disp."}
              </label>
              <button
                type="button"
                onClick={() => removeTier(i)}
                className="w-10 h-10 rounded-lg bg-white/5 border border-white/15 flex items-center justify-center active:scale-90"
                aria-label="Eliminar fase"
              >
                <X className="w-4 h-4 text-white/60" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addTier}
            className="h-10 rounded-lg border border-dashed border-white/20 text-white/60 text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95 hover:text-white hover:border-white/40"
            data-testid="admin-add-tier"
          >
            <Plus className="w-3.5 h-3.5" /> Añadir fase de precio
          </button>
        </div>

        {initial?.id && (
          <label className="flex items-center gap-2 pt-1 text-xs text-white/70 cursor-pointer">
            <input
              type="checkbox"
              checked={notifyOnSave}
              onChange={(e) => setNotifyOnSave(e.target.checked)}
              className="w-4 h-4"
              data-testid="admin-notify-toggle"
            />
            <BellRing className="w-3.5 h-3.5 text-qv-secondary" />
            Enviar notificación push cuando cambie el estado (recomendado)
          </label>
        )}
      </div>

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
  const [statsId, setStatsId] = useState(null);
  const [city, setCity] = useState("Palma de Mallorca");
  const [tab, setTab] = useState("upcoming");

  const scope = tab === "past" ? "past" : "upcoming";
  const { data: events = [], isLoading } = useQuery({
    queryKey: ["admin-events", city, scope],
    queryFn: async () => (await api.get("/admin/events", { params: { city, scope } })).data,
  });

  // Broken/at-risk buy links (surfaced in the "Enlaces" tab so the owner can fix
  // them with the pencil before anyone clicks a dead link).
  const { data: linkHealth } = useQuery({
    queryKey: ["admin-link-health", city],
    queryFn: async () => (await api.get("/admin/link-health", { params: { city } })).data,
    refetchOnWindowFocus: false,
  });
  const brokenCount = linkHealth?.total || 0;

  // Push alert toggle for at-risk links + on-demand check.
  const { data: brokenAlerts } = useQuery({
    queryKey: ["admin-broken-alerts"],
    queryFn: async () => (await api.get("/admin/settings/broken-link-alerts")).data,
  });
  const toggleBrokenAlerts = useMutation({
    mutationFn: async (enabled) => (await api.put("/admin/settings/broken-link-alerts", { enabled })).data,
    onMutate: async (enabled) => {
      await qc.cancelQueries({ queryKey: ["admin-broken-alerts"] });
      const prev = qc.getQueryData(["admin-broken-alerts"]);
      qc.setQueryData(["admin-broken-alerts"], { enabled });
      return { prev };
    },
    onSuccess: (d) => toast.success(d.enabled ? "Te avisaremos por push 🔔" : "Avisos de enlaces desactivados"),
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["admin-broken-alerts"], ctx.prev);
      toast.error("No se pudo actualizar");
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin-broken-alerts"] }),
  });
  const checkNow = useMutation({
    mutationFn: async () => (await api.post("/admin/link-health/notify")).data,
    onSuccess: (d) => {
      toast.success(d.notified_new > 0 ? `Aviso enviado: ${d.notified_new} nuevo(s)` : "Comprobado. Sin novedades ✅");
      qc.invalidateQueries({ queryKey: ["admin-link-health"] });
    },
    onError: () => toast.error("No se pudo comprobar"),
  });

  const del = useMutation({
    mutationFn: async (id) => (await api.delete(`/admin/events/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-events"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      toast.success("Evento borrado");
    },
  });

  const triggerMoment = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/events/${id}/moment/trigger`)).data,
    onSuccess: (data) => toast.success(`⚡ Momento lanzado a ${data.notified} usuarios`),
    onError: () => toast.error("No se pudo lanzar"),
  });

  // Signup alerts (notify admin on every new registration) — ON by default.
  const { data: signupAlerts } = useQuery({
    queryKey: ["admin-signup-alerts"],
    queryFn: async () => (await api.get("/admin/settings/signup-alerts")).data,
  });
  const toggleSignupAlerts = useMutation({
    mutationFn: async (enabled) => (await api.put("/admin/settings/signup-alerts", { enabled })).data,
    onMutate: async (enabled) => {
      await qc.cancelQueries({ queryKey: ["admin-signup-alerts"] });
      const prev = qc.getQueryData(["admin-signup-alerts"]);
      qc.setQueryData(["admin-signup-alerts"], { enabled });
      return { prev };
    },
    onSuccess: (d) => toast.success(d.enabled ? "Te avisaremos de cada registro 🔔" : "Avisos de registro desactivados"),
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["admin-signup-alerts"], ctx.prev);
      toast.error("No se pudo actualizar");
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["admin-signup-alerts"] }),
  });

  const byDay = useMemo(() => {
    const m = {};
    events.forEach((e) => { (m[e.date] = m[e.date] || []).push(e); });
    return Object.entries(m).sort(([a], [b]) => a.localeCompare(b));
  }, [events]);

  const TABS = [
    { value: "upcoming", label: "Próximas", icon: CalendarDays },
    { value: "momentos", label: "Momentos", icon: Zap },
    { value: "enlaces", label: "Enlaces", icon: LinkIcon },
    { value: "past", label: "Pasadas", icon: History },
  ];

  const Row = ({ ev, showMoment }) => (
    <div className="flex gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`admin-event-${ev.id}`}>
      {ev.image_url && (
        <img src={mediaThumb(ev.image_url, 200)} alt={ev.name} loading="lazy" className="w-16 h-16 rounded-xl object-cover shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="font-semibold truncate">{ev.name}</p>
        <p className="text-white/40 text-sm truncate">{ev.venue} · {ev.date}{ev.time ? ` · ${ev.time}` : ""}</p>
        <span className="inline-flex items-center gap-1 text-xs mt-1 text-white/50">
          {ev.has_commission ? <><Ticket className="w-3 h-3" /> Comisión</> : <><ExternalLink className="w-3 h-3" /> Info</>}
        </span>
      </div>
      <div className="flex flex-col gap-2">
        <button data-testid={`admin-stats-${ev.id}`} onClick={() => setStatsId(ev.id)} className="w-9 h-9 rounded-full bg-qv-secondary/20 flex items-center justify-center" title="Ver stats">
          <BarChart3 className="w-4 h-4 text-qv-secondary" />
        </button>
        {tab !== "past" && (
          <button data-testid={`admin-edit-${ev.id}`} onClick={() => setEditing(ev)} className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center">
            <Pencil className="w-4 h-4 text-white/80" />
          </button>
        )}
        {showMoment && (
          <button
            data-testid={`admin-moment-${ev.id}`}
            onClick={() => { if (window.confirm(`¿Lanzar 'El Momento' a los asistentes de ${ev.name}?`)) triggerMoment.mutate(ev.id); }}
            className="w-9 h-9 rounded-full bg-yellow-300/20 flex items-center justify-center"
            title="Lanzar Momento"
          >
            <Zap className="w-4 h-4 text-yellow-300" />
          </button>
        )}
        <button data-testid={`admin-delete-${ev.id}`} onClick={() => del.mutate(ev.id)} className="w-9 h-9 rounded-full bg-qv-primary/20 flex items-center justify-center">
          <Trash2 className="w-4 h-4 text-qv-primary" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen qv-app-bg">
      <div className="max-w-md mx-auto min-h-screen pb-10">
        <header className="px-5 pt-8 pb-4 flex items-center gap-3">
          <button data-testid="admin-back" onClick={() => navigate("/feed")} className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="font-display text-2xl font-black tracking-tighter">Panel admin</h1>
            <p className="text-white/40 text-xs">{events.length} fiestas · {CITIES.find((c) => c.value === city)?.label}</p>
          </div>
          <button
            data-testid="admin-money-btn"
            onClick={() => navigate("/admin/dinero")}
            className="ml-auto h-10 px-4 rounded-full bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-bold text-sm flex items-center justify-center gap-1.5 active:scale-95"
          >
            💶 Dinero
          </button>
        </header>

        {/* Ajuste: avisos de nuevos registros */}
        <div className="px-5 mb-3">
          <div className="flex items-center gap-3 rounded-2xl bg-white/[0.04] border border-white/10 p-3" data-testid="admin-signup-alerts-row">
            <div className="w-9 h-9 rounded-full bg-qv-secondary/20 flex items-center justify-center shrink-0">
              <BellRing className="w-4.5 h-4.5 text-qv-secondary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-white leading-tight">Avisarme de nuevos registros</p>
              <p className="text-white/45 text-xs">Recibe una notificación cuando alguien se registre.</p>
            </div>
            <Switch
              data-testid="admin-signup-alerts-switch"
              checked={!!signupAlerts?.enabled}
              onCheckedChange={(v) => toggleSignupAlerts.mutate(v)}
            />
          </div>
        </div>

        {/* City selector — a separate admin per city */}
        <div className="px-5 mb-3 flex gap-2 overflow-x-auto no-scrollbar">
          {CITIES.map((c) => (
            <button
              key={c.value}
              data-testid={`admin-city-${c.value}`}
              onClick={() => setCity(c.value)}
              className={`shrink-0 h-9 px-4 rounded-full text-sm font-semibold transition-colors ${city === c.value ? "bg-qv-primary text-white" : "bg-white/5 text-white/60 border border-white/10"}`}
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* Sub-sections within Fiestas */}
        <div className="px-5 mb-4 flex gap-2">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.value}
                data-testid={`admin-tab-${t.value}`}
                onClick={() => setTab(t.value)}
                className={`relative flex-1 h-10 rounded-xl text-sm font-semibold flex items-center justify-center gap-1.5 transition-colors ${tab === t.value ? "bg-white/15 text-white" : "bg-white/5 text-white/50"}`}
              >
                <Icon className="w-4 h-4" /> {t.label}
                {t.value === "enlaces" && brokenCount > 0 && (
                  <span data-testid="admin-broken-badge" className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-qv-primary text-white text-[10px] font-black flex items-center justify-center">
                    {brokenCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {tab === "upcoming" && (
          <div className="px-5">
            <Dialog open={openNew} onOpenChange={setOpenNew}>
              <DialogTrigger asChild>
                <button data-testid="admin-new-event" className="h-12 w-full rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform mb-4">
                  <Plus className="w-5 h-5" /> Nueva fiesta
                </button>
              </DialogTrigger>
              <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle className="font-display">Nueva fiesta</DialogTitle></DialogHeader>
                <EventForm cityDefault={city} onSaved={() => setOpenNew(false)} />
              </DialogContent>
            </Dialog>
          </div>
        )}

        {tab === "enlaces" && (
          <div className="px-5 flex flex-col gap-3" data-testid="admin-link-health">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
              <p className="text-sm text-white/70">
                Revisados <b className="text-white">{linkHealth?.checked ?? 0}</b> eventos próximos ·{" "}
                <b className={brokenCount > 0 ? "text-qv-primary" : "text-emerald-400"}>{brokenCount}</b> con enlace en riesgo
              </p>
              <p className="text-[11px] text-white/40 mt-1 leading-snug">
                Detectamos enlaces de afiliado que pueden estar rotos (código desincronizado) o vacíos. Ábrelo y pon el enlace correcto con el lápiz — tu enlace manual siempre manda.
              </p>
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/10">
                <div className="flex items-center gap-2 min-w-0">
                  <BellRing className="w-4 h-4 text-qv-secondary shrink-0" />
                  <span className="text-sm text-white/80 truncate">Avisarme por push cuando haya nuevos</span>
                </div>
                <Switch
                  data-testid="admin-broken-alerts-toggle"
                  checked={brokenAlerts?.enabled ?? true}
                  onCheckedChange={(v) => toggleBrokenAlerts.mutate(v)}
                />
              </div>
              <button
                data-testid="admin-check-now"
                onClick={() => checkNow.mutate()}
                disabled={checkNow.isPending}
                className="mt-3 w-full h-10 rounded-xl bg-white/5 border border-white/15 text-white/80 text-sm font-semibold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
              >
                {checkNow.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Comprobar ahora"}
              </button>
            </div>
            {brokenCount === 0 ? (
              <p className="py-8 text-center text-white/40 text-sm">Todo en orden. No hay enlaces en riesgo. ✅</p>
            ) : (
              (linkHealth?.events || []).map((e) => (
                <div key={e.event_id} className="flex gap-3 bg-white/5 border border-qv-primary/30 rounded-2xl p-3" data-testid={`admin-broken-${e.event_id}`}>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold truncate">{e.name}</p>
                    <p className="text-white/40 text-sm truncate">{e.venue} · {e.date}{e.time ? ` · ${e.time}` : ""}</p>
                    <span className="inline-block text-[10px] font-bold uppercase tracking-wide mt-1 px-2 py-0.5 rounded-full bg-qv-primary/20 text-qv-primary">
                      {e.reason === "empty" ? "Sin enlace" : "Feed afiliado caducado (revisa token)"}
                    </span>
                    <p className="text-[11px] text-white/40 break-all mt-1">{e.commission_url || "(vacío)"}</p>
                  </div>
                  <button
                    data-testid={`admin-fix-${e.event_id}`}
                    onClick={() => navigate(`/event/${e.event_id}`)}
                    className="self-center shrink-0 h-9 px-3 rounded-xl bg-qv-primary text-white text-xs font-bold flex items-center gap-1.5 active:scale-95"
                  >
                    <Pencil className="w-3.5 h-3.5" /> Arreglar
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {tab !== "enlaces" && (isLoading ? (
          <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-qv-primary" /></div>
        ) : events.length === 0 ? (
          <p className="px-5 py-10 text-center text-white/40 text-sm">
            {tab === "past" ? "No hay fiestas pasadas todavía." : "No hay fiestas en esta ciudad."}
          </p>
        ) : tab === "momentos" ? (
          <div className="px-5 flex flex-col gap-4">
            {byDay.map(([day, evs]) => (
              <div key={day}>
                <p className="text-xs font-bold uppercase tracking-widest text-qv-secondary mb-2">{day}</p>
                <div className="flex flex-col gap-3">
                  {evs.map((ev) => <Row key={ev.id} ev={ev} showMoment />)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-5 flex flex-col gap-3">
            {events.map((ev) => <Row key={ev.id} ev={ev} showMoment={false} />)}
          </div>
        ))}

        <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
          <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle className="font-display">Editar fiesta</DialogTitle></DialogHeader>
            {editing && <EventForm initial={editing} onSaved={() => setEditing(null)} />}
          </DialogContent>
        </Dialog>

        {statsId && <AdminEventStats eventId={statsId} onClose={() => setStatsId(null)} />}
      </div>
    </div>
  );
}
