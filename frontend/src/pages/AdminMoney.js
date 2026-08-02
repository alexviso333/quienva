import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import api from "@/lib/api";
import { ArrowLeft, Eye, Star, PartyPopper, MousePointerClick, Ticket, Euro, Building2, Megaphone, Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";

function Metric({ icon: Icon, n, label, color = "text-white" }) {
  return (
    <div className="flex-1 text-center">
      <Icon className={`w-4 h-4 mx-auto mb-1 ${color}`} />
      <p className="font-display text-lg font-black text-white leading-none">{n}</p>
      <p className="text-[9px] text-white/40 mt-0.5 uppercase tracking-wide">{label}</p>
    </div>
  );
}

export default function AdminMoney() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("funnel");

  const { data: funnel, isLoading, refetch } = useQuery({
    queryKey: ["admin-funnel"],
    queryFn: async () => (await api.get("/admin/funnel")).data,
  });
  const { data: venueReport } = useQuery({
    queryKey: ["admin-venue-report"],
    queryFn: async () => (await api.get("/admin/venue-report")).data,
    enabled: tab === "venues",
  });

  const notify = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/events/${id}/notify-interested`, { message: "" })).data,
    onSuccess: (d) => toast.success(`📣 Aviso enviado a ${d.notified} personas`),
    onError: () => toast.error("No se pudo enviar"),
  });
  const lowStock = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/events/${id}/notify-low-stock`)).data,
    onSuccess: (d) => toast.success(`⚡ 'Pocas entradas' a ${d.notified} personas`),
    onError: () => toast.error("No se pudo enviar"),
  });

  const totals = funnel?.totals;

  const copyReport = () => {
    if (!venueReport) return;
    const lines = venueReport.venues.map((v) =>
      `• ${v.venue}: ${v.views} vistas · ${v.going} van · ${v.clicks} clics · ${v.tickets} entradas · ${v.commission}€`
    );
    navigator.clipboard?.writeText(`Informe ¿Quién va?\n${lines.join("\n")}`);
    toast.success("Informe copiado — pégalo donde quieras");
  };

  return (
    <div className="min-h-screen qv-app-bg">
      <div className="max-w-md mx-auto min-h-screen pb-10">
        <header className="px-5 pt-8 pb-4 flex items-center gap-3">
          <button data-testid="money-back" onClick={() => navigate("/admin")} className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="font-display text-2xl font-black tracking-tighter">Dinero</h1>
            <p className="text-white/40 text-xs">Embudo de ventas y comisiones</p>
          </div>
        </header>

        {/* Big € card */}
        <div className="px-5">
          <div className="rounded-2xl border border-qv-primary/40 bg-gradient-to-br from-[#1a0a12] to-black p-5 text-center">
            <p className="text-xs uppercase tracking-widest text-qv-secondary font-bold">Comisión estimada (próximos)</p>
            <p className="font-display text-5xl font-black text-white mt-1">{totals ? totals.commission : "—"}€</p>
            {totals && (
              <div className="flex items-center justify-center gap-4 mt-3 text-xs text-white/60">
                <span>{totals.tickets} entradas</span>
                <span>·</span>
                <span>{totals.clicks} clics</span>
                <span>·</span>
                <span>{totals.going} van</span>
              </div>
            )}
          </div>
        </div>

        <div className="px-5 flex gap-1.5 mt-4 mb-3 p-1 rounded-2xl bg-white/5 border border-white/10">
          <button data-testid="money-tab-funnel" onClick={() => setTab("funnel")} className={`flex-1 py-2 rounded-xl text-xs font-bold ${tab === "funnel" ? "bg-white text-black" : "text-white/60"}`}>Por evento</button>
          <button data-testid="money-tab-venues" onClick={() => setTab("venues")} className={`flex-1 py-2 rounded-xl text-xs font-bold ${tab === "venues" ? "bg-white text-black" : "text-white/60"}`}>Por local</button>
        </div>

        {tab === "funnel" ? (
          <div className="px-5 flex flex-col gap-3">
            {isLoading ? (
              <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-qv-primary" /></div>
            ) : (funnel?.rows || []).length === 0 ? (
              <p className="text-white/40 text-sm text-center py-8">Aún no hay datos de eventos próximos.</p>
            ) : (
              funnel.rows.map((r) => (
                <div key={r.id} className="rounded-2xl bg-white/[0.03] border border-white/10 p-3" data-testid={`funnel-row-${r.id}`}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-white truncate">{r.name}</p>
                      <p className="text-white/40 text-xs truncate">{r.venue} · {r.date}{r.price ? ` · ${Math.round(r.price)}€` : ""}</p>
                    </div>
                    <span className="shrink-0 font-display font-black text-qv-secondary">{r.est_commission}€</span>
                  </div>
                  <div className="flex items-center gap-1 bg-black/30 rounded-xl p-2">
                    <Metric icon={Eye} n={r.views} label="vistas" color="text-white/50" />
                    <Metric icon={Star} n={r.interested} label="interés" color="text-qv-secondary" />
                    <Metric icon={PartyPopper} n={r.going} label="van" color="text-qv-primary" />
                    <Metric icon={MousePointerClick} n={r.clicks} label="clics" color="text-white/70" />
                    <Metric icon={Ticket} n={r.tickets} label="entradas" color="text-green-400" />
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button
                      data-testid={`funnel-notify-${r.id}`}
                      onClick={() => notify.mutate(r.id)}
                      className="flex-1 h-9 rounded-xl bg-qv-secondary/15 text-qv-secondary border border-qv-secondary/30 text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95"
                    >
                      <Megaphone className="w-3.5 h-3.5" /> Avisar interesados
                    </button>
                    <button
                      onClick={() => lowStock.mutate(r.id)}
                      className="flex-1 h-9 rounded-xl bg-yellow-300/15 text-yellow-300 border border-yellow-300/30 text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95"
                    >
                      <Zap className="w-3.5 h-3.5" /> Pocas entradas
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="px-5 flex flex-col gap-3">
            <button onClick={copyReport} className="h-10 rounded-xl bg-white/10 text-white font-bold text-sm active:scale-95">
              📋 Copiar informe para la discoteca
            </button>
            {(venueReport?.venues || []).map((v, i) => (
              <div key={i} className="rounded-2xl bg-white/[0.03] border border-white/10 p-3" data-testid={`venue-row-${i}`}>
                <div className="flex items-center justify-between mb-2">
                  <p className="font-semibold text-white flex items-center gap-1.5"><Building2 className="w-4 h-4 text-qv-secondary" /> {v.venue}</p>
                  <span className="font-display font-black text-qv-secondary">{v.commission}€</span>
                </div>
                <div className="flex items-center gap-1 bg-black/30 rounded-xl p-2">
                  <Metric icon={Eye} n={v.views} label="vistas" color="text-white/50" />
                  <Metric icon={PartyPopper} n={v.going} label="van" color="text-qv-primary" />
                  <Metric icon={MousePointerClick} n={v.clicks} label="clics" color="text-white/70" />
                  <Metric icon={Ticket} n={v.tickets} label="entradas" color="text-green-400" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
