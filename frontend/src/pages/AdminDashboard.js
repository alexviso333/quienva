import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Users, PartyPopper, TrendingUp, Star, ShieldCheck, ShieldOff, Trash2, Search, Loader2, Calendar, Ticket, BookOpen, UserCheck } from "lucide-react";
import { toast } from "sonner";

function StatBox({ icon: Icon, value, label, color = "text-qv-primary" }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3">
      <div className="flex items-center justify-between">
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <p className="font-display text-2xl font-bold text-white mt-1">{value ?? 0}</p>
      <p className="text-white/50 text-xs">{label}</p>
    </div>
  );
}

export default function AdminDashboard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");

  const { data: stats } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: async () => (await api.get("/admin/stats")).data,
    staleTime: 30_000,
  });

  const { data: users = [], isLoading: loadingUsers } = useQuery({
    queryKey: ["admin-users", search],
    queryFn: async () => (await api.get("/admin/users", { params: { search } })).data,
    staleTime: 15_000,
  });

  const setRole = useMutation({
    mutationFn: async ({ userId, role }) => (await api.put(`/admin/users/${userId}/role`, { role })).data,
    onSuccess: () => {
      toast.success("Rol actualizado");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  const deleteUser = useMutation({
    mutationFn: async (userId) => (await api.delete(`/admin/users/${userId}`)).data,
    onSuccess: () => {
      toast.success("Usuario eliminado");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
    },
    onError: () => toast.error("Error al borrar"),
  });

  return (
    <div className="min-h-screen qv-app-bg pb-16" data-testid="admin-dashboard">
      <div className="sticky top-0 z-20 qv-glass px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate("/profile")}><ArrowLeft className="w-5 h-5 text-white" /></button>
        <h1 className="font-display text-lg font-bold">Panel avanzado</h1>
        <button
          onClick={() => navigate("/admin")}
          className="ml-auto text-xs text-qv-secondary font-semibold flex items-center gap-1"
        >
          <Ticket className="w-3.5 h-3.5" /> Fiestas
        </button>
      </div>

      {/* Stats grid */}
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

      {/* Top events */}
      <div className="px-4 mt-6">
        <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-qv-primary" /> Top fiestas próximas
        </h2>
        {stats?.top_events && stats.top_events.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            {stats.top_events.map((ev) => (
              <button
                key={ev.id}
                onClick={() => navigate(`/event/${ev.id}`)}
                className="text-left rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3 active:scale-[0.99]"
              >
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm text-white truncate">{ev.name}</p>
                  <p className="text-white/50 text-xs truncate">{ev.venue} · {ev.date}</p>
                </div>
                <span className="text-qv-primary font-bold text-sm">{ev.signups}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-white/40 text-sm">Aún no hay apuntados a próximas fiestas.</p>
        )}
      </div>

      {/* Genres */}
      {stats?.genres && stats.genres.length > 0 && (
        <div className="px-4 mt-6">
          <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2">
            <Star className="w-4 h-4 text-qv-secondary" /> Géneros populares
          </h2>
          <div className="flex flex-wrap gap-1.5">
            {stats.genres.map((g) => (
              <span key={g.genre} className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-white/90 font-semibold">
                {g.genre} · <span className="text-qv-primary">{g.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Users */}
      <div className="px-4 mt-6">
        <h2 className="font-display text-base font-bold text-white mb-2 flex items-center gap-2">
          <Users className="w-4 h-4 text-qv-secondary" /> Usuarios
        </h2>
        <div className="relative mb-2">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <Input
            data-testid="admin-search-users"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nombre o email..."
            className="h-10 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40"
          />
        </div>
        {loadingUsers ? (
          <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {users.map((u) => (
              <div key={u.user_id} className="rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3" data-testid={`admin-user-${u.user_id}`}>
                <AvatarCircle name={u.name} picture={u.picture} size={38} />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm text-white truncate flex items-center gap-1.5">
                    {u.name}
                    {u.role === "admin" && (
                      <span className="text-[9px] uppercase tracking-widest bg-qv-secondary/20 text-qv-secondary px-1.5 py-0.5 rounded-full">
                        Admin
                      </span>
                    )}
                  </p>
                  <p className="text-white/40 text-xs truncate">{u.email}</p>
                  <p className="text-white/40 text-[10px] mt-0.5">
                    {u._stats?.attended || 0} estuve · {u._stats?.going || 0} voy · {u._stats?.friends || 0} amigos
                  </p>
                </div>
                <button
                  onClick={() => setRole.mutate({ userId: u.user_id, role: u.role === "admin" ? "user" : "admin" })}
                  className="p-2 rounded-lg bg-white/5 hover:bg-white/10"
                  title={u.role === "admin" ? "Quitar admin" : "Hacer admin"}
                  data-testid={`admin-toggle-role-${u.user_id}`}
                >
                  {u.role === "admin"
                    ? <ShieldOff className="w-4 h-4 text-white/60" />
                    : <ShieldCheck className="w-4 h-4 text-qv-secondary" />}
                </button>
                <button
                  onClick={() => {
                    if (window.confirm(`¿Borrar a ${u.name}?`)) deleteUser.mutate(u.user_id);
                  }}
                  className="p-2 rounded-lg bg-white/5 hover:bg-red-500/20"
                  title="Borrar usuario"
                  data-testid={`admin-delete-${u.user_id}`}
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            ))}
            {users.length === 0 && !loadingUsers && (
              <p className="text-center text-white/40 text-sm py-8">Ningún usuario coincide</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
