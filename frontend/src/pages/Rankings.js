import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { useAuth } from "@/context/AuthContext";
import { Trophy, Loader2, ArrowLeft, Users, MapPin, Globe2 } from "lucide-react";

const TABS = [
  { key: "friends", label: "Amigos", icon: Users },
  { key: "city", label: "Ciudad", icon: MapPin },
  { key: "world", label: "Mundial", icon: Globe2 },
];

const MEDAL = { 1: "🥇", 2: "🥈", 3: "🥉" };

export default function Rankings() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("friends");

  const { data: list = [], isLoading } = useQuery({
    queryKey: ["ranking", tab],
    queryFn: async () => (await api.get(`/rankings/${tab}`)).data,
    staleTime: 30_000,
  });

  const myIndex = list.findIndex((e) => e.user_id === user?.user_id);

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3 flex items-center gap-3">
        <button
          data-testid="ranking-back"
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center text-white active:scale-90 transition-transform"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <p className="text-xs tracking-[0.25em] uppercase text-yellow-300 font-bold flex items-center gap-1.5">
            <Trophy className="w-3.5 h-3.5" /> Top
          </p>
          <h1 className="font-display text-3xl font-black tracking-tighter">Ranking<span className="text-qv-primary">.</span></h1>
        </div>
      </header>

      <div className="flex gap-2 px-5 pb-3" data-testid="ranking-tabs">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            data-testid={`ranking-tab-${key}`}
            onClick={() => setTab(key)}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-full px-3 py-2 text-xs font-bold whitespace-nowrap transition-colors duration-300 ${
              tab === key ? "bg-white text-black" : "bg-white/5 border border-white/10 text-white/70"
            }`}
          >
            <Icon className="w-3.5 h-3.5" /> {label}
          </button>
        ))}
      </div>

      {tab === "city" && (
        <p className="text-white/40 text-xs px-5 mb-2">Ciudad: {user?.city || "Palma de Mallorca"}</p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="w-7 h-7 text-qv-primary animate-spin" /></div>
      ) : list.length === 0 ? (
        <p className="text-center text-white/40 py-16 px-6">Aún no hay puntos en este ranking.</p>
      ) : (
        <div className="px-4 flex flex-col gap-2" data-testid="ranking-list">
          {list.map((e, i) => {
            const isMe = e.user_id === user?.user_id;
            return (
              <button
                key={e.user_id}
                data-testid={`ranking-row-${e.rank}`}
                onClick={() => navigate(isMe ? "/profile" : `/users/${e.user_id}`)}
                className={`flex items-center gap-3 rounded-2xl p-3 text-left transition-transform active:scale-[0.99] ${
                  isMe ? "bg-qv-primary/15 border border-qv-primary/40" : "bg-white/5 border border-white/10"
                }`}
              >
                <div className="w-8 text-center font-display font-black text-lg text-white/80">
                  {MEDAL[e.rank] || `#${e.rank}`}
                </div>
                <AvatarCircle name={e.name} picture={e.picture} size={42} ring={i < 3} />
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-white truncate">{e.name} {isMe && <span className="text-qv-primary text-xs ml-1">· TÚ</span>}</p>
                  <p className="text-white/50 text-xs">@{e.username || ""}</p>
                </div>
                <div className="text-right">
                  <p className="font-display font-black text-yellow-300 text-lg leading-none">{e.points.toLocaleString("es-ES")}</p>
                  <p className="text-[10px] text-white/40 uppercase tracking-widest">pts</p>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {myIndex >= 0 && list.length > 20 && myIndex > 20 && (
        <p className="text-center text-white/40 text-xs mt-6">Tu posición: #{list[myIndex].rank}</p>
      )}
    </AppShell>
  );
}
