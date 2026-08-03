import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Users, PartyPopper, TrendingUp, Star, ShieldCheck, ShieldOff, Trash2, Search, Loader2, Calendar, Ticket, BookOpen, UserCheck, Trophy, MessageCircle, Images, Zap, Check, X, BarChart3, Radio, Euro, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from "recharts";
import AdminMomentPanel from "@/components/AdminMomentPanel";
import AdminScrapersPanel from "@/components/AdminScrapersPanel";
import AdminVenuesPanel from "@/components/AdminVenuesPanel";
import AdminScrapeChangelog from "@/components/AdminScrapeChangelog";
import AdminEventStats from "@/components/AdminEventStats";

function StatBox({ icon: Icon, value, label, color = "text-qv-primary" }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3">
      <Icon className={`w-4 h-4 ${color}`} />
      <p className="font-display text-2xl font-bold text-white mt-1">{value ?? 0}</p>
      <p className="text-white/50 text-xs">{label}</p>
    </div>
  );
}

const TABS = [
  { id: "resumen", label: "Resumen", icon: BarChart3 },
  { id: "fiestas", label: "Fiestas", icon: PartyPopper },
  { id: "scrapers", label: "Scrapers", icon: Radio },
  { id: "dinero", label: "Dinero", icon: Euro },
  { id: "usuarios", label: "Usuarios", icon: Users },
];

const SALE_LABEL = {
  no_a_la_venta: { t: "Próx.", c: "bg-white/10 text-white/60" },
  a_la_venta: { t: "A la venta", c: "bg-emerald-400/20 text-emerald-300" },
  pocas_entradas: { t: "Pocas", c: "bg-orange-400/25 text-orange-200" },
  agotado: { t: "Agotado", c: "bg-white/10 text-white/50" },
};

export default function AdminDashboard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState("resumen");
  const [search, setSearch] = useState("");
  const [eventSearch, setEventSearch] = useState("");
  const [statsEventId, setStatsEventId] = useState(null);

  const { data: stats } = useQuery({ queryKey: ["admin-stats"], queryFn: async () => (await api.get("/admin/stats")).data, staleTime: 30_000 });
  const { data: dashboard } = useQuery({ queryKey: ["admin-dashboard"], queryFn: async () => (await api.get("/admin/dashboard")).data, staleTime: 30_000 });
  const { data: pendingTickets = [] } = useQuery({ queryKey: ["admin-tickets", "pending"], queryFn: async () => (await api.get("/admin/tickets?status=pending")).data, staleTime: 20_000 });
  const { data: funnel } = useQuery({ queryKey: ["admin-funnel", "all"], queryFn: async () => (await api.get("/admin/funnel?scope=all")).data, staleTime: 30_000, enabled: tab === "fiestas" || tab === "dinero" });

  const confirmTicket = useMutation({
    mutationFn: async ({ purchase_id, confirmed }) => (await api.post("/admin/tickets/confirm", { purchase_id, confirmed })).data,
    onSuccess: () => { toast.success("Actualizado"); qc.invalidateQueries({ queryKey: ["admin-tickets"] }); qc.invalidateQueries({ queryKey: ["admin-dashboard"] }); },
    onError: () => toast.error("Error"),
  });

  const { data: users = [], isLoading: loadingUsers } = useQuery({ queryKey: ["admin-users", search], queryFn: async () => (await api.get("/admin/users", { params: { search } })).data, staleTime: 15_000, enabled: tab === "usuarios" });

  const setRole = useMutation({
    mutationFn: async ({ userId, role }) => (await api.put(`/admin/users/${userId}/role`, { role })).data,
    onSuccess: () => { toast.success("Rol actualizado"); qc.invalidateQueries({ queryKey: ["admin-users"] }); },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });
  const deleteUser = useMutation({
    mutationFn: async (userId) => (await api.delete(`/admin/users/${userId}`)).data,
    onSuccess: () => { toast.success("Usuario eliminado"); qc.invalidateQueries({ queryKey: ["admin-users"] }); qc.invalidateQueries({ queryKey: ["admin-stats"] }); },
    onError: () => toast.error("Error al borrar"),
  });

  const funnelRows = (funnel?.rows || []).filter((r) => !eventSearch || r.name.toLowerCase().includes(eventSearch.toLowerCase()) || (r.venue || "").toLowerCase().includes(eventSearch.toLowerCase()));

  return (
    <div className="min-h-screen qv-app-bg pb-16" data-testid="admin-dashboard">
      <div className="sticky top-0 z-20 qv-glass px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate("/profile")}><ArrowLeft className="w-5 h-5 text-white" /></button>
        <h1 className="font-display text-lg font-bold">Panel de control</h1>
        <button onClick={() => navigate("/admin")} className="ml-auto text-xs text-qv-secondary font-semibold flex items-center gap-1">
          <Ticket className="w-3.5 h-3.5" /> Fiestas
        </button>
      </div>

      {/* Tab bar */}
      <div className="sticky top-[52px] z-10 qv-glass px-2 py-2 flex gap-1 overflow-x-auto hide-scrollbar border-b border-white/10">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              data-testid={`admin-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5 transition-colors ${active ? "bg-white text-black" : "bg-white/5 text-white/60"}`}
            >
              <Icon className="w-3.5 h-3.5" /> {t.label}
            </button>
          );
        })}
      </div>

      {/* ---------------- RESUMEN ---------------- */}
      {tab === "resumen" && (
        <>
          <div className="px-4 pt-4 grid grid-cols-3 gap-2">
            <StatBox icon={Users} value={stats?.totals.users} label="usuarios" color="text-qv-secondary" />
            <StatBox icon={UserCheck} value={stats?.totals.active_week} label="activos 7d" color="text-emerald-400" />
            <StatBox icon={PartyPopper} value={stats?.totals.upcoming} label="próximas" color="text-qv-primary" />
            <StatBox icon={Ticket} value={stats?.totals.going} label='"voy"' color="text-orange-300" />
            <StatBox icon={Star} value={stats?.totals.interested} label="me interesa" color="text-yellow-300" />
            <StatBox icon={Calendar} value={stats?.totals.attended} label="estuve" color="text-fuchsia-300" />
            <StatBox icon={BookOpen} value={stats?.totals.stories} label="stories" color="text-blue-300" />
            <StatBox icon={Users} value={stats?.totals.friendships} label="amistades" color="text-green-300" />
            <StatBox icon={TrendingUp} value={stats?.totals.events} label="total fiestas" color="text-pink-300" />
          </div>

          {dashboard?.activity_30d && (
            <div className="px-4 mt-6">
              <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-qv-secondary" /> Actividad · 30 días</h2>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                <div style={{ width: "100%", height: 220 }}>
                  <ResponsiveContainer>
                    <LineChart data={dashboard.activity_30d.map((d) => ({ ...d, label: new Date(d.date + "T00:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short" }) }))} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                      <CartesianGrid stroke="#ffffff10" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "#ffffff60", fontSize: 10 }} interval={4} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#ffffff60", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} width={30} />
                      <Tooltip contentStyle={{ background: "#121215", border: "1px solid #ffffff25", borderRadius: 12, color: "#fff" }} />
                      <Legend wrapperStyle={{ fontSize: 11, color: "#ffffff80" }} />
                      <Line type="monotone" dataKey="signups" name="Registros" stroke="#00F0FF" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="voys" name="Voys" stroke="#FF0055" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="stories" name="Stories" stroke="#FFD93D" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="captures" name="Momentos" stroke="#B45CFF" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {dashboard?.extras && (
            <div className="px-4 mt-3 grid grid-cols-4 gap-2">
              <StatBox icon={MessageCircle} value={dashboard.extras.dms} label="DM" color="text-blue-300" />
              <StatBox icon={Users} value={dashboard.extras.groups} label="grupos" color="text-emerald-300" />
              <StatBox icon={Images} value={dashboard.extras.album_items} label="álbum" color="text-fuchsia-300" />
              <StatBox icon={Zap} value={dashboard.extras.captures} label="momentos" color="text-yellow-300" />
            </div>
          )}

          {dashboard?.top_users && dashboard.top_users.length > 0 && (
            <div className="px-4 mt-6">
              <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2"><Trophy className="w-4 h-4 text-yellow-300" /> Top usuarios por puntos</h2>
              <div className="flex flex-col gap-1.5" data-testid="admin-top-users">
                {dashboard.top_users.map((u) => (
                  <button key={u.user_id} onClick={() => navigate(`/users/${u.user_id}`)} className="text-left rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3 active:scale-[0.99]">
                    <span className="w-8 text-center font-display font-black text-white/80">#{u.rank}</span>
                    <AvatarCircle name={u.name} picture={u.picture} size={34} ring={u.rank <= 3} />
                    <div className="flex-1 min-w-0"><p className="font-bold text-sm text-white truncate">{u.name}</p><p className="text-white/40 text-[10px] truncate">{u.city}</p></div>
                    <span className="font-display font-black text-yellow-300 text-sm">{u.points.toLocaleString("es-ES")}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {stats?.genres && stats.genres.length > 0 && (
            <div className="px-4 mt-6">
              <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2"><Star className="w-4 h-4 text-qv-secondary" /> Géneros populares</h2>
              <div className="flex flex-wrap gap-1.5">
                {stats.genres.map((g) => (
                  <span key={g.genre} className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-white/90 font-semibold">{g.genre} · <span className="text-qv-primary">{g.count}</span></span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ---------------- FIESTAS ---------------- */}
      {tab === "fiestas" && (
        <div className="px-4 pt-4">
          <AdminMomentPanel />
          <h2 className="font-display text-base font-bold text-white mb-2 mt-2 flex items-center gap-2"><PartyPopper className="w-4 h-4 text-qv-primary" /> Todas las fiestas</h2>
          <p className="text-white/40 text-xs mb-3">Toca una fiesta para ver estadísticas completas e historial de precio/estado.</p>
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input data-testid="admin-event-search" value={eventSearch} onChange={(e) => setEventSearch(e.target.value)} placeholder="Buscar fiesta o local..." className="h-10 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40" />
          </div>
          {!funnel ? (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {funnelRows.map((r) => {
                const sl = SALE_LABEL[r.sale_state] || SALE_LABEL.no_a_la_venta;
                return (
                  <button key={r.id} data-testid={`admin-event-row-${r.id}`} onClick={() => setStatsEventId(r.id)} className="text-left rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3 active:scale-[0.99]">
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm text-white truncate">{r.name}</p>
                      <p className="text-white/45 text-[11px] truncate">{r.venue} · {r.date}</p>
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-white/50">
                        <span className="flex items-center gap-0.5"><Users className="w-3 h-3 text-qv-primary" />{r.going}</span>
                        <span className="flex items-center gap-0.5"><Star className="w-3 h-3 text-yellow-300" />{r.interested}</span>
                        <span className="flex items-center gap-0.5"><Ticket className="w-3 h-3 text-emerald-300" />{r.tickets}</span>
                        <span className={`px-1.5 py-0.5 rounded-full ${sl.c}`}>{r.price ? `${Math.round(r.price)}€ · ` : ""}{sl.t}</span>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-white/30 shrink-0" />
                  </button>
                );
              })}
              {funnelRows.length === 0 && <p className="text-center text-white/40 text-sm py-8">Ninguna fiesta coincide</p>}
            </div>
          )}
        </div>
      )}

      {/* ---------------- SCRAPERS ---------------- */}
      {tab === "scrapers" && (
        <div className="px-4 pt-4">
          <AdminScrapeChangelog />
          <AdminScrapersPanel />
          <AdminVenuesPanel />
        </div>
      )}

      {/* ---------------- DINERO ---------------- */}
      {tab === "dinero" && (
        <div className="px-4 pt-4">
          {funnel?.totals && (
            <div className="grid grid-cols-2 gap-2 mb-4">
              <StatBox icon={Ticket} value={funnel.totals.tickets} label="entradas" color="text-emerald-300" />
              <StatBox icon={Euro} value={`${Math.round(funnel.totals.commission)}€`} label="comisión est." color="text-yellow-300" />
              <StatBox icon={Users} value={funnel.totals.going} label="van (total)" color="text-qv-primary" />
              <StatBox icon={TrendingUp} value={funnel.totals.clicks} label="clics entrada" color="text-orange-300" />
            </div>
          )}
          <button onClick={() => navigate("/admin/dinero")} className="w-full h-12 rounded-2xl bg-yellow-300/15 border border-yellow-300/40 text-yellow-200 font-bold flex items-center justify-center gap-2 active:scale-95" data-testid="open-money-panel">
            <Euro className="w-4 h-4" /> Abrir embudo de dinero completo
          </button>
          <p className="text-white/40 text-xs mt-3">Toca una fiesta en la pestaña “Fiestas” para ver su embudo individual (vistas → interés → van → clics → entradas → €).</p>
        </div>
      )}

      {/* ---------------- USUARIOS ---------------- */}
      {tab === "usuarios" && (
        <div className="px-4 pt-4">
          {pendingTickets.length > 0 && (
            <div className="mb-6">
              <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2"><Ticket className="w-4 h-4 text-orange-300" /> Entradas pendientes <span className="text-xs font-normal text-white/40">({pendingTickets.length})</span></h2>
              <div className="flex flex-col gap-1.5" data-testid="admin-pending-tickets">
                {pendingTickets.map((t) => (
                  <div key={t.id} className="rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3">
                    <div className="flex-1 min-w-0"><p className="font-semibold text-sm text-white truncate">{t.event?.name}</p><p className="text-white/50 text-xs truncate">{t.user?.name} · {new Date(t.created_at).toLocaleString("es-ES")}</p></div>
                    <button onClick={() => confirmTicket.mutate({ purchase_id: t.id, confirmed: true })} className="w-9 h-9 rounded-full bg-emerald-500/20 flex items-center justify-center active:scale-90" data-testid={`ticket-confirm-${t.id}`}><Check className="w-4 h-4 text-emerald-300" /></button>
                    <button onClick={() => confirmTicket.mutate({ purchase_id: t.id, confirmed: false })} className="w-9 h-9 rounded-full bg-white/5 flex items-center justify-center active:scale-90" data-testid={`ticket-reject-${t.id}`}><X className="w-4 h-4 text-white/60" /></button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2"><Users className="w-4 h-4 text-qv-secondary" /> Usuarios</h2>
          <div className="relative mb-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input data-testid="admin-search-users" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por nombre o email..." className="h-10 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40" />
          </div>
          {loadingUsers ? (
            <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {users.map((u) => (
                <div key={u.user_id} className="rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3" data-testid={`admin-user-${u.user_id}`}>
                  <AvatarCircle name={u.name} picture={u.picture} size={38} />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm text-white truncate flex items-center gap-1.5">{u.name}{u.role === "admin" && <span className="text-[9px] uppercase tracking-widest bg-qv-secondary/20 text-qv-secondary px-1.5 py-0.5 rounded-full">Admin</span>}</p>
                    <p className="text-white/40 text-xs truncate">{u.email}</p>
                    <p className="text-white/40 text-[10px] mt-0.5">{u._stats?.attended || 0} estuve · {u._stats?.going || 0} voy · {u._stats?.friends || 0} amigos</p>
                  </div>
                  <button onClick={() => setRole.mutate({ userId: u.user_id, role: u.role === "admin" ? "user" : "admin" })} className="p-2 rounded-lg bg-white/5 hover:bg-white/10" data-testid={`admin-toggle-role-${u.user_id}`}>{u.role === "admin" ? <ShieldOff className="w-4 h-4 text-white/60" /> : <ShieldCheck className="w-4 h-4 text-qv-secondary" />}</button>
                  <button onClick={() => { if (window.confirm(`¿Borrar a ${u.name}?`)) deleteUser.mutate(u.user_id); }} className="p-2 rounded-lg bg-white/5 hover:bg-red-500/20" data-testid={`admin-delete-${u.user_id}`}><Trash2 className="w-4 h-4 text-red-400" /></button>
                </div>
              ))}
              {users.length === 0 && !loadingUsers && <p className="text-center text-white/40 text-sm py-8">Ningún usuario coincide</p>}
            </div>
          )}
        </div>
      )}

      {statsEventId && <AdminEventStats eventId={statsEventId} onClose={() => setStatsEventId(null)} />}
    </div>
  );
}
