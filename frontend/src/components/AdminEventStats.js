import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api, { mediaThumb } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  X, Eye, Star, Ticket, Users, Zap, Images, Bell, Flame, Euro, TrendingUp,
  TrendingDown, Sparkles, Lock, Loader2, ExternalLink, MousePointerClick, Heart,
} from "lucide-react";
import { toast } from "sonner";

const HIST_META = {
  created: { label: "Creada", icon: Sparkles, cls: "text-emerald-300 bg-emerald-400/15" },
  price_up: { label: "Subió precio", icon: TrendingUp, cls: "text-orange-300 bg-orange-400/15" },
  price_down: { label: "Bajó precio", icon: TrendingDown, cls: "text-sky-300 bg-sky-400/15" },
  on_sale: { label: "A la venta", icon: Ticket, cls: "text-emerald-300 bg-emerald-400/15" },
  low_stock: { label: "Pocas entradas", icon: Flame, cls: "text-orange-300 bg-orange-400/15" },
  state: { label: "Cambio de estado", icon: Flame, cls: "text-orange-300 bg-orange-400/15" },
  sold_out: { label: "Agotado", icon: Lock, cls: "text-white/60 bg-white/10" },
  pricing_edited: { label: "Precio editado", icon: Euro, cls: "text-fuchsia-300 bg-fuchsia-400/15" },
};

function when(iso) {
  try { return new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

function Metric({ icon: Icon, value, label, color }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-2.5">
      <Icon className={`w-4 h-4 ${color}`} />
      <p className="font-display text-xl font-bold text-white mt-1 leading-none">{value ?? 0}</p>
      <p className="text-white/45 text-[10px] mt-0.5">{label}</p>
    </div>
  );
}

function People({ title, list, color }) {
  if (!list || list.length === 0) return null;
  return (
    <div>
      <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-1.5">{title} · {list.length}</p>
      <div className="flex flex-wrap gap-1.5">
        {list.map((p) => (
          <div key={p.user_id} className="flex items-center gap-1.5 rounded-full bg-white/[0.05] border border-white/10 pl-1 pr-2.5 py-1">
            <AvatarCircle name={p.name} picture={p.picture} size={20} ring={false} />
            <span className="text-white/80 text-[11px] font-medium max-w-[90px] truncate">{p.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminEventStats({ eventId, onClose }) {
  const navigate = useNavigate();
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["admin-event-stats", eventId],
    queryFn: async () => (await api.get(`/admin/events/${eventId}/stats`)).data,
    enabled: !!eventId,
  });

  const notifyInterested = useMutation({
    mutationFn: async () => (await api.post(`/admin/events/${eventId}/notify-interested`, {})).data,
    onSuccess: (d) => toast.success(`Avisados ${d.notified ?? ""} interesados`),
    onError: () => toast.error("No se pudo avisar"),
  });
  const notifyLowStock = useMutation({
    mutationFn: async () => (await api.post(`/admin/events/${eventId}/notify-low-stock`)).data,
    onSuccess: (d) => toast.success(`Aviso 'pocas entradas' enviado (${d.notified ?? 0})`),
    onError: () => toast.error("No se pudo avisar"),
  });
  const triggerMoment = useMutation({
    mutationFn: async () => (await api.post(`/admin/events/${eventId}/moment/trigger`)).data,
    onSuccess: (d) => { toast.success(`El Momento lanzado (${d.notified ?? 0} avisados)`); refetch(); },
    onError: () => toast.error("No se pudo lanzar"),
  });

  const ev = data?.event;
  const f = data?.funnel || {};
  const people = data?.people || {};
  const history = data?.history || [];

  return (
    <Dialog open={!!eventId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-[#0b0b0d] border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden max-h-[88vh] flex flex-col">
        {isLoading || !ev ? (
          <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
        ) : (
          <>
            {/* Header */}
            <div className="relative shrink-0">
              <div className="h-28 w-full overflow-hidden">
                {ev.image_url ? (
                  <img src={mediaThumb(ev.image_url, 600)} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] to-[#0a1a1f]" />
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-[#0b0b0d] to-transparent" />
              </div>
              <button onClick={onClose} className="absolute top-3 right-3 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center" data-testid="event-stats-close">
                <X className="w-5 h-5 text-white" />
              </button>
              <div className="absolute bottom-2 left-4 right-4">
                <h3 className="font-display font-black text-white text-lg leading-tight line-clamp-1">{ev.name}</h3>
                <p className="text-white/60 text-xs">{ev.venue} · {ev.date} · {ev.source === "scraper" ? "auto" : "manual"}</p>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto hide-scrollbar p-4 space-y-5">
              {/* Pricing snapshot */}
              <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-white/40 font-bold">Precio / estado</p>
                  <p className="font-display text-xl font-black text-white">
                    {ev.current_price ? `${Math.round(ev.current_price)}€` : "—"}
                    <span className="text-white/50 text-sm font-semibold ml-2 capitalize">{(ev.sale_state || "").replace(/_/g, " ")}</span>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-widest text-yellow-300/70 font-bold">Comisión est.</p>
                  <p className="font-display text-lg font-black text-yellow-300">{Math.round(f.est_commission || 0)}€</p>
                </div>
              </div>

              {/* Funnel metrics */}
              <div>
                <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Embudo</p>
                <div className="grid grid-cols-3 gap-2">
                  <Metric icon={Eye} value={f.views} label="vistas" color="text-blue-300" />
                  <Metric icon={Heart} value={f.interested} label="interesados" color="text-yellow-300" />
                  <Metric icon={Users} value={f.going} label="van" color="text-qv-primary" />
                  <Metric icon={MousePointerClick} value={f.clicks} label="clics entrada" color="text-orange-300" />
                  <Metric icon={Ticket} value={f.tickets} label="tienen entrada" color="text-emerald-300" />
                  <Metric icon={Bell} value={f.followers} label="siguen" color="text-fuchsia-300" />
                  <Metric icon={Star} value={f.attended} label="estuvieron" color="text-fuchsia-200" />
                  <Metric icon={Images} value={f.album_items} label="álbum" color="text-sky-300" />
                  <Metric icon={Zap} value={f.captures} label="momentos" color="text-yellow-200" />
                </div>
                <p className="text-white/40 text-[11px] mt-2">Conversión clic→entrada: <span className="text-white font-bold">{f.conversion_pct || 0}%</span></p>
              </div>

              {/* Admin quick actions */}
              <div>
                <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Acciones</p>
                <div className="grid grid-cols-2 gap-2">
                  <button onClick={() => notifyInterested.mutate()} className="h-10 rounded-xl bg-yellow-300/15 border border-yellow-300/30 text-yellow-200 text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95" data-testid="act-notify-interested">
                    <Bell className="w-3.5 h-3.5" /> Avisar interesados
                  </button>
                  <button onClick={() => notifyLowStock.mutate()} className="h-10 rounded-xl bg-orange-400/15 border border-orange-400/30 text-orange-200 text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95" data-testid="act-low-stock">
                    <Flame className="w-3.5 h-3.5" /> Pocas entradas
                  </button>
                  <button onClick={() => triggerMoment.mutate()} className="h-10 rounded-xl bg-qv-secondary/15 border border-qv-secondary/30 text-qv-secondary text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95" data-testid="act-moment">
                    <Zap className="w-3.5 h-3.5" /> Lanzar Momento
                  </button>
                  <button onClick={() => navigate(`/event/${eventId}`)} className="h-10 rounded-xl bg-white/5 border border-white/15 text-white text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95" data-testid="act-view">
                    <ExternalLink className="w-3.5 h-3.5" /> Ver ficha
                  </button>
                </div>
              </div>

              {/* People */}
              <People title="Van" list={people.going} />
              <People title="Interesados" list={people.interested} />
              <People title="Estuvieron" list={people.attended} />

              {/* History timeline */}
              <div>
                <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Historial de precio y estado</p>
                {history.length === 0 ? (
                  <p className="text-white/40 text-xs italic">Sin cambios registrados todavía.</p>
                ) : (
                  <div className="space-y-1.5">
                    {history.map((h) => {
                      const meta = HIST_META[h.kind] || HIST_META.state;
                      const Icon = meta.icon;
                      let detail = "";
                      if (h.new_price != null && h.old_price != null) detail = `${Math.round(h.old_price)}€ → ${Math.round(h.new_price)}€`;
                      else if (h.new_price != null) detail = `→ ${Math.round(h.new_price)}€`;
                      else if (h.new_state) detail = `${(h.old_state || "").replace(/_/g, " ")} → ${(h.new_state || "").replace(/_/g, " ")}`;
                      return (
                        <div key={h.id} className="flex items-center gap-2.5 p-2 rounded-xl bg-white/[0.03] border border-white/5">
                          <span className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${meta.cls}`}><Icon className="w-3.5 h-3.5" /></span>
                          <div className="flex-1 min-w-0">
                            <p className="text-white text-xs font-semibold">{meta.label} {detail && <span className="text-white/50 font-normal capitalize">· {detail}</span>}</p>
                            <p className="text-white/35 text-[10px]">{when(h.created_at)} · {h.source === "admin" ? "manual" : "scraper"}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
