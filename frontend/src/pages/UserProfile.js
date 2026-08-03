import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { BadgesPanel } from "@/components/BadgesPanel";
import { UserActionsMenu } from "@/components/ReportBlock";
import { ArrowLeft, Loader2, MessageSquare, UserPlus, Clock, Check, Trophy, Flame, Calendar, Star } from "lucide-react";
import { toast } from "sonner";

function StatMini({ icon: Icon, value, label, color = "text-qv-primary" }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex flex-col items-center gap-1">
      <Icon className={`w-4 h-4 ${color}`} />
      <span className="font-display text-xl font-bold text-white">{value ?? 0}</span>
      <span className="text-white/50 text-[10px] uppercase tracking-widest">{label}</span>
    </div>
  );
}

export default function UserProfile() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["user-badges", userId],
    queryFn: async () => (await api.get(`/users/${userId}/badges`)).data,
    staleTime: 60_000,
  });

  const addFriend = useMutation({
    mutationFn: async () => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: () => {
      toast.success("Solicitud enviada ✨");
      qc.invalidateQueries({ queryKey: ["user-badges", userId] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "No se pudo enviar"),
  });

  const acceptFriend = useMutation({
    mutationFn: async () => {
      const reqs = (await api.get("/friends/requests")).data;
      const match = reqs.find((r) => r.user?.user_id === userId);
      if (!match) throw new Error("No hay solicitud");
      return (await api.post("/friends/respond", { request_id: match.request_id, accept: true })).data;
    },
    onSuccess: () => {
      toast.success("¡Ahora sois amigos!");
      qc.invalidateQueries({ queryKey: ["user-badges", userId] });
      qc.invalidateQueries({ queryKey: ["friends"] });
    },
    onError: () => toast.error("Error"),
  });

  if (isLoading) {
    return (
      <AppShell>
        {/* Skeleton for perceived speed */}
        <div className="px-5 pt-8 animate-pulse">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-full bg-white/5" />
            <div className="h-4 w-24 bg-white/5 rounded" />
          </div>
          <div className="flex flex-col items-center gap-3">
            <div className="w-24 h-24 rounded-full bg-white/5" />
            <div className="h-5 w-40 bg-white/5 rounded" />
            <div className="h-3 w-24 bg-white/5 rounded" />
            <div className="h-11 w-32 bg-white/5 rounded-full mt-1" />
          </div>
          <div className="grid grid-cols-4 gap-2 mt-6">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="aspect-square rounded-2xl bg-white/[0.03]" />
            ))}
          </div>
        </div>
      </AppShell>
    );
  }

  if (isError || !data) {
    return (
      <AppShell>
        <div className="px-5 py-20 text-center">
          <p className="text-white/60">Usuario no encontrado.</p>
          <button onClick={() => navigate(-1)} className="mt-4 text-qv-secondary text-sm">Volver</button>
        </div>
      </AppShell>
    );
  }

  const { user, stats, points, is_friend, is_self, friend_status } = data;
  const canDM = is_friend || is_self;

  return (
    <AppShell>
      <div className="sticky top-0 z-20 qv-glass px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} data-testid="userprofile-back">
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <span className="font-display text-lg font-bold flex-1">Perfil</span>
        {!is_self && <UserActionsMenu userId={userId} userName={user.name} />}
      </div>

      <div className="px-5 pt-4 flex flex-col items-center gap-3">
        <AvatarCircle name={user.name} picture={user.picture} size={92} />
        <div className="text-center">
          <h1 className="font-display text-2xl font-bold">{user.name}</h1>
          {user.username && <p className="text-white/50 text-sm">@{user.username}</p>}
          {user.city && <p className="text-white/40 text-xs mt-1">{user.city}</p>}
        </div>
        {user.bio && <p className="text-white/70 text-sm text-center max-w-xs">{user.bio}</p>}

        {/* Action buttons based on friendship status */}
        <div className="flex flex-wrap justify-center gap-2 mt-1">
          {friend_status === "none" && (
            <button
              data-testid="userprofile-addfriend-btn"
              onClick={() => addFriend.mutate()}
              disabled={addFriend.isPending}
              className="h-11 px-5 rounded-full bg-qv-primary text-white font-bold flex items-center gap-2 active:scale-95 transition-transform disabled:opacity-50"
            >
              <UserPlus className="w-4 h-4" /> {addFriend.isPending ? "Enviando…" : "Añadir amigo"}
            </button>
          )}
          {friend_status === "pending_out" && (
            <div className="h-11 px-5 rounded-full bg-white/5 border border-white/15 text-white/70 font-semibold flex items-center gap-2">
              <Clock className="w-4 h-4" /> Solicitud enviada
            </div>
          )}
          {friend_status === "pending_in" && (
            <button
              data-testid="userprofile-accept-btn"
              onClick={() => acceptFriend.mutate()}
              className="h-11 px-5 rounded-full bg-qv-secondary text-black font-bold flex items-center gap-2 active:scale-95"
            >
              <Check className="w-4 h-4" /> Aceptar solicitud
            </button>
          )}
          {canDM && !is_self && (
            <button
              data-testid="userprofile-message-btn"
              onClick={() => navigate(`/chats/dm/${userId}`)}
              className="h-11 px-5 rounded-full bg-qv-primary text-white font-bold flex items-center gap-2 active:scale-95 transition-transform"
            >
              <MessageSquare className="w-4 h-4" /> Enviar mensaje
            </button>
          )}
        </div>
      </div>

      {/* Public stats card — always visible */}
      <div className="px-5 mt-6 grid grid-cols-4 gap-2">
        <StatMini icon={Trophy} value={stats.total_events} label="Fiestas" color="text-yellow-300" />
        <StatMini icon={Flame} value={stats.day_streak} label="Días" color="text-orange-400" />
        <StatMini icon={Calendar} value={stats.week_streak} label="Semanas" color="text-qv-secondary" />
        <StatMini icon={Star} value={stats.genres_count} label="Géneros" color="text-fuchsia-300" />
      </div>

      {points && (
        <div className="px-5 mt-3">
          <div className="rounded-2xl border border-yellow-300/30 bg-yellow-300/10 p-3 flex items-center gap-3">
            <Trophy className="w-5 h-5 text-yellow-300" />
            <div>
              <p className="text-[10px] uppercase tracking-widest text-yellow-300 font-bold">Puntos totales</p>
              <p className="font-display text-2xl font-black text-white leading-none">{points.total.toLocaleString("es-ES")}</p>
            </div>
          </div>
        </div>
      )}

      {/* Badges — full for friends, only earned for non-friends */}
      <div className="px-5 mt-6 pb-24">
        {is_friend || is_self ? (
          <BadgesPanel userId={userId} />
        ) : (
          <>
            <p className="text-white/40 text-xs uppercase tracking-widest font-bold mb-3">
              Insignias · {(data.earned || []).length}
            </p>
            {(data.earned || []).length === 0 ? (
              <p className="text-white/40 text-sm italic text-center py-8">Todavía no ha ganado ninguna insignia.</p>
            ) : (
              <div className="grid grid-cols-4 gap-2">
                {data.earned.map((b) => (
                  <div key={b.id} className="aspect-square rounded-2xl bg-gradient-to-br from-amber-500 to-yellow-300 p-2 flex flex-col items-center justify-center text-center">
                    <span className="text-2xl">{b.emoji}</span>
                    <span className="mt-1 text-[10px] font-bold leading-tight text-black">{b.name}</span>
                  </div>
                ))}
              </div>
            )}
            <p className="text-white/40 text-[11px] text-center mt-6 italic">
              Añádelo/a como amigo para ver toda su actividad e insignias detalladas.
            </p>
          </>
        )}
      </div>
    </AppShell>
  );
}
