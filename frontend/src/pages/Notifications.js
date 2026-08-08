import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import {
  Bell, UserPlus, PartyPopper, Check, CheckCheck, CalendarDays, AlarmClock,
  Star, Heart, MessageCircle, Sparkles, Ticket, Flame, Lock, TrendingUp, Zap,
} from "lucide-react";

/**
 * Bandeja de Novedades — full unified inbox of every push the user gets.
 * Groups by day (Hoy / Ayer / fecha larga) and enriches each row with an
 * icon + color that matches the notification type.
 */
const TYPE_META = {
  // ticket / event feed
  new_event:         { icon: Sparkles,     tint: "text-fuchsia-300 bg-fuchsia-400/15" },
  tickets_on_sale:   { icon: Ticket,       tint: "text-emerald-300 bg-emerald-400/15" },
  tickets_low_stock: { icon: Flame,        tint: "text-orange-300 bg-orange-400/20" },
  tickets_sold_out:  { icon: Lock,         tint: "text-white/60 bg-white/10" },
  tickets_price_up:  { icon: TrendingUp,   tint: "text-yellow-300 bg-yellow-400/15" },
  moment_prompt:     { icon: Zap,          tint: "text-black bg-qv-secondary" },
  // social
  friend_going:      { icon: PartyPopper,  tint: "text-pink-300 bg-pink-400/15" },
  friend_request:    { icon: UserPlus,     tint: "text-cyan-300 bg-cyan-400/15" },
  friend_accept:     { icon: Check,        tint: "text-emerald-300 bg-emerald-400/15" },
  story_reaction:    { icon: Heart,        tint: "text-rose-300 bg-rose-400/15" },
  event_message:     { icon: MessageCircle,tint: "text-blue-300 bg-blue-400/15" },
  // digests / reminders
  weekly_digest:     { icon: CalendarDays, tint: "text-white bg-white/10" },
  event_reminder:    { icon: AlarmClock,   tint: "text-yellow-300 bg-yellow-400/15" },
  interested_reminder:{ icon: Star,        tint: "text-yellow-300 bg-yellow-400/15" },
  weekend_recap:     { icon: Sparkles,     tint: "text-fuchsia-300 bg-fuchsia-400/15" },
};

import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

function timeAgo(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return i18n.t("notifs.now");
  if (diff < 3600) return i18n.t("notifs.ago_min", { n: Math.floor(diff / 60) });
  if (diff < 86400) return i18n.t("notifs.ago_hour", { n: Math.floor(diff / 3600) });
  return i18n.t("notifs.ago_day", { n: Math.floor(diff / 86400) });
}

function dayKey(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayLabel(k) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const toKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (k === toKey(today)) return i18n.t("notifs.today");
  if (k === toKey(yesterday)) return i18n.t("notifs.yesterday");
  const d = new Date(k);
  return d.toLocaleDateString(i18n.language, { weekday: "long", day: "numeric", month: "long" });
}

export default function Notifications() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: notifs = [], isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => (await api.get("/notifications")).data,
    staleTime: 60_000,
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
     
  }, [notifs.length]);

  // Group by day (preserves API's DESC-by-created_at order)
  const groups = useMemo(() => {
    const g = new Map();
    for (const n of notifs) {
      const k = dayKey(n.created_at);
      if (!g.has(k)) g.set(k, []);
      g.get(k).push(n);
    }
    return Array.from(g.entries());
  }, [notifs]);

  const targetFor = (n) => {
    if (n.data?.event_id) return `/event/${n.data.event_id}`;
    if (n.type === "friend_request" || n.type === "friend_accept") return "/friends";
    if (n.type === "story_reaction") return "/profile";
    if (n.data?.url) return n.data.url;
    return null;
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4 flex items-center justify-between">
        <div>
          <h1 className="font-display text-4xl font-black tracking-tighter">
            {t("notifs.title")}<span className="text-qv-primary">.</span>
          </h1>
          <p className="text-white/40 text-xs mt-0.5">{t("notifs.subtitle")}</p>
        </div>
        {notifs.length > 0 && (
          <button
            data-testid="mark-all-read"
            onClick={() => markAll.mutate()}
            className="text-xs text-white/50 flex items-center gap-1.5"
          >
            <CheckCheck className="w-4 h-4" /> {t("notifs.mark_read")}
          </button>
        )}
      </header>

      <div className="px-5 flex flex-col gap-4 pb-20">
        {isLoading ? null : notifs.length === 0 ? (
          <div className="text-center py-24" data-testid="notifs-empty">
            <Bell className="w-12 h-12 text-white/25 mx-auto mb-4" />
            <p className="text-white/50">{t("notifs.empty_title")}</p>
            <p className="text-white/35 text-sm mt-1">{t("notifs.empty_sub")}</p>
          </div>
        ) : (
          groups.map(([k, items]) => (
            <section key={k}>
              <h2 className="text-white/50 text-[11px] font-bold uppercase tracking-widest mb-2 first-letter:uppercase">
                {dayLabel(k)}
              </h2>
              <div className="flex flex-col gap-2">
                {items.map((n) => {
                  const meta = TYPE_META[n.type] || { icon: Bell, tint: "text-white/70 bg-white/10" };
                  const Icon = meta.icon;
                  const target = targetFor(n);
                  return (
                    <div
                      key={n.id}
                      data-testid={`notif-${n.id}`}
                      onClick={() => target && navigate(target)}
                      className={`flex items-center gap-3 rounded-2xl p-3.5 border ${target ? "cursor-pointer active:scale-[0.99]" : ""} ${
                        n.read ? "bg-white/5 border-white/10" : "bg-qv-primary/10 border-qv-primary/30"
                      }`}
                    >
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${meta.tint}`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white/90 leading-snug">{n.message}</p>
                        <p className="text-white/40 text-xs mt-0.5">{timeAgo(n.created_at)}</p>
                      </div>
                      {!n.read && <span className="w-2.5 h-2.5 rounded-full bg-qv-primary shrink-0" />}
                    </div>
                  );
                })}
              </div>
            </section>
          ))
        )}
      </div>
    </AppShell>
  );
}
