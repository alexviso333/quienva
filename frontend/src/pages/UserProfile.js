import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { BadgesPanel } from "@/components/BadgesPanel";
import { ArrowLeft, Loader2, MessageSquare } from "lucide-react";

export default function UserProfile() {
  const { userId } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["user-badges", userId],
    queryFn: async () => (await api.get(`/users/${userId}/badges`)).data,
  });

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex justify-center py-24">
          <Loader2 className="w-6 h-6 animate-spin text-qv-primary" />
        </div>
      </AppShell>
    );
  }

  if (isError || !data) {
    return (
      <AppShell>
        <div className="px-5 py-20 text-center">
          <p className="text-white/60">No puedes ver este perfil.</p>
          <button onClick={() => navigate(-1)} className="mt-4 text-qv-secondary text-sm">Volver</button>
        </div>
      </AppShell>
    );
  }

  const { user, stats } = data;

  return (
    <AppShell>
      <div className="sticky top-0 z-20 qv-glass px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} data-testid="userprofile-back">
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <span className="font-display text-lg font-bold">Perfil</span>
      </div>

      <div className="px-5 pt-4 flex flex-col items-center gap-3">
        <AvatarCircle name={user.name} picture={user.picture} size={92} />
        <h1 className="font-display text-2xl font-bold text-center">{user.name}</h1>
        <p className="text-white/50 text-sm">
          {stats.total_events} fiestas · {stats.friends_count} amigos
        </p>
        <button
          data-testid="userprofile-message-btn"
          onClick={() => navigate(`/chats/dm/${userId}`)}
          className="h-11 px-5 rounded-full bg-qv-primary text-white font-bold flex items-center gap-2 active:scale-95 transition-transform"
        >
          <MessageSquare className="w-4 h-4" /> Enviar mensaje
        </button>
      </div>

      <div className="px-5 mt-6 pb-24">
        <BadgesPanel userId={userId} />
      </div>
    </AppShell>
  );
}
