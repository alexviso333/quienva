import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import api from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Ticket, PartyPopper, Sparkles, X } from "lucide-react";
import { useState } from "react";

function timeAgo(ts, t) {
  if (!ts) return "";
  const d = new Date(ts);
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return t ? t("feedextras.now") : "ahora";
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

/** Horizontal strip of what friends are doing — the social heartbeat. */
export function FriendsActivity() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["activity"],
    queryFn: async () => (await api.get("/me/activity")).data,
    staleTime: 30_000,
    retry: false,
  });
  const items = data?.items || [];
  if (items.length === 0) return null;
  return (
    <div className="pb-3" data-testid="friends-activity">
      <p className="px-5 text-xs uppercase tracking-widest text-white/40 font-bold mb-2">{t("feedextras.your_friends")}</p>
      <div className="flex overflow-x-auto hide-scrollbar gap-2 px-4">
        {items.map((it, i) => (
          <button
            key={i}
            onClick={() => navigate(`/event/${it.event_id}`)}
            data-testid={`activity-item-${i}`}
            className="shrink-0 w-44 text-left rounded-2xl bg-white/[0.04] border border-white/10 p-3 active:scale-95 transition-transform"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <AvatarCircle name={it.user.name} picture={it.user.picture} size={26} />
              <span className="text-xs font-bold text-white truncate flex-1">{it.user.name?.split(" ")[0]}</span>
              <span className="text-[10px] text-white/30">{timeAgo(it.ts, t)}</span>
            </div>
            <p className="text-xs text-white/70 leading-tight">
              {it.type === "ticket" ? (
                <span className="text-qv-secondary font-semibold flex items-center gap-1"><Ticket className="w-3 h-3" /> {t("feedextras.has_ticket")}</span>
              ) : (
                <span className="text-qv-primary font-semibold flex items-center gap-1"><PartyPopper className="w-3 h-3" /> {t("feedextras.going")}</span>
              )}{" "}
              <Trans i18nKey="feedextras.suffix" values={{ event: it.event_name }} components={{ 1: <span className="text-white font-semibold" /> }} />
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Weekly recap card — dopamine + FOMO. Dismissable per week. */
export function RecapCard() {
  const { t } = useTranslation();
  const weekKey = `qv_recap_dismissed_${new Date().getFullYear()}_${Math.floor(Date.now() / (7 * 864e5))}`;
  const [hidden, setHidden] = useState(() => localStorage.getItem(weekKey) === "1");
  const { data } = useQuery({
    queryKey: ["recap"],
    queryFn: async () => (await api.get("/me/recap")).data,
    staleTime: 5 * 60_000,
    retry: false,
  });
  if (hidden || !data?.has_activity) return null;
  const dismiss = () => { localStorage.setItem(weekKey, "1"); setHidden(true); };
  return (
    <div className="px-4 pb-3" data-testid="recap-card">
      <div className="relative rounded-2xl overflow-hidden border border-qv-primary/30 bg-gradient-to-br from-[#1a0a12] via-[#0d0d0d] to-[#0a1416] p-4">
        <button onClick={dismiss} className="absolute top-2 right-2 w-7 h-7 rounded-full bg-white/10 flex items-center justify-center">
          <X className="w-3.5 h-3.5 text-white/60" />
        </button>
        <p className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold text-qv-secondary">
          <Sparkles className="w-3.5 h-3.5" /> {t("feedextras.your_week")}
        </p>
        <div className="flex items-center gap-5 mt-2">
          <Stat n={data.went} label={t("feedextras.plans")} />
          <Stat n={data.photos} label={t("feedextras.photos")} />
          <Stat n={data.new_friends} label={t("feedextras.friends")} />
        </div>
        {data.friends_plans > 0 && (
          <p className="text-white/60 text-xs mt-2.5">
            <Trans i18nKey="feedextras.group_plans" count={data.friends_plans} values={{ count: data.friends_plans }} components={{ 1: <span className="text-white font-semibold" /> }} />
          </p>
        )}
      </div>
    </div>
  );
}

function Stat({ n, label }) {
  return (
    <div className="text-center">
      <p className="font-display text-2xl font-black text-white leading-none">{n}</p>
      <p className="text-[10px] text-white/50 mt-0.5">{label}</p>
    </div>
  );
}
