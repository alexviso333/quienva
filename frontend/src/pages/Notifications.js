import { useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { Bell, UserPlus, PartyPopper, Check, CheckCheck, CalendarDays, AlarmClock, Star } from "lucide-react";

const ICONS = {
  friend_going: PartyPopper,
  friend_request: UserPlus,
  friend_accept: Check,
  weekly_digest: CalendarDays,
  event_reminder: AlarmClock,
  interested_reminder: Star,
};

function timeAgo(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "ahora";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return `hace ${Math.floor(diff / 86400)} d`;
}

export default function Notifications() {
  const qc = useQueryClient();
  const { data: notifs = [], isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => (await api.get("/notifications")).data,
  });

  const markAll = useMutation({
    mutationFn: async () => (await api.post("/notifications/read-all")).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["unread-count"] });
    },
  });

  useEffect(() => {
    const hasUnread = notifs.some((n) => !n.read);
    if (hasUnread) {
      const t = setTimeout(() => markAll.mutate(), 1200);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notifs.length]);

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4 flex items-center justify-between">
        <h1 className="font-display text-4xl font-black tracking-tighter">
          Avisos<span className="text-qv-primary">.</span>
        </h1>
        {notifs.length > 0 && (
          <button
            data-testid="mark-all-read"
            onClick={() => markAll.mutate()}
            className="text-xs text-white/50 flex items-center gap-1.5"
          >
            <CheckCheck className="w-4 h-4" /> Leídas
          </button>
        )}
      </header>

      <div className="px-5 flex flex-col gap-2">
        {isLoading ? null : notifs.length === 0 ? (
          <div className="text-center py-24" data-testid="notifs-empty">
            <Bell className="w-12 h-12 text-white/25 mx-auto mb-4" />
            <p className="text-white/50">Sin novedades por ahora.</p>
            <p className="text-white/35 text-sm mt-1">Aquí verás cuando tus amigos digan "voy".</p>
          </div>
        ) : (
          notifs.map((n) => {
            const Icon = ICONS[n.type] || Bell;
            return (
              <div
                key={n.id}
                data-testid={`notif-${n.id}`}
                className={`flex items-center gap-3 rounded-2xl p-3.5 border ${
                  n.read ? "bg-white/5 border-white/10" : "bg-qv-primary/10 border-qv-primary/30"
                }`}
              >
                <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${n.read ? "bg-white/10" : "bg-qv-primary"}`}>
                  <Icon className={`w-5 h-5 ${n.read ? "text-white/60" : "text-white"}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white/90 leading-snug">{n.message}</p>
                  <p className="text-white/40 text-xs mt-0.5">{timeAgo(n.created_at)}</p>
                </div>
                {!n.read && <span className="w-2.5 h-2.5 rounded-full bg-qv-primary shrink-0" />}
              </div>
            );
          })
        )}
      </div>
    </AppShell>
  );
}
