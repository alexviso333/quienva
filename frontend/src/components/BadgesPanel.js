import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import api from "@/lib/api";
import { Lock, Flame, Calendar, Trophy, Star } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const TIER_STYLES = {
  bronze: "from-amber-700 to-amber-500",
  silver: "from-slate-400 to-slate-200",
  gold: "from-yellow-400 to-amber-300",
  platinum: "from-fuchsia-400 to-qv-secondary",
};

function BadgeTile({ badge, earned, onClick }) {
  return (
    <button
      onClick={onClick}
      data-testid={`badge-${badge.id}`}
      className={`relative aspect-square rounded-2xl border p-2 flex flex-col items-center justify-center text-center transition-transform active:scale-95 ${
        earned
          ? `border-white/20 bg-gradient-to-br ${TIER_STYLES[badge.tier] || TIER_STYLES.bronze}`
          : "border-white/10 bg-white/[0.03] opacity-60"
      }`}
    >
      {!earned && <Lock className="absolute top-1.5 right-1.5 w-3 h-3 text-white/40" />}
      <span className={`text-3xl ${earned ? "" : "grayscale opacity-70"}`}>{badge.emoji}</span>
      <span className={`mt-1 text-[10px] font-bold leading-tight ${earned ? "text-black" : "text-white/70"}`}>
        {badge.name}
      </span>
    </button>
  );
}

function StatCard({ icon: Icon, value, label, color = "text-qv-primary" }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex flex-col items-start gap-1">
      <Icon className={`w-4 h-4 ${color}`} />
      <span className="font-display text-2xl font-bold text-white">{value}</span>
      <span className="text-white/50 text-xs">{label}</span>
    </div>
  );
}

/**
 * Badges & achievements panel — used both in own /profile and in other users' profiles.
 * If userId is null/undefined → shows current user's badges.
 */
export function BadgesPanel({ userId }) {
  const endpoint = userId ? `/users/${userId}/badges` : "/me/badges";
  const { data, isLoading } = useQuery({
    queryKey: ["badges", userId || "me"],
    queryFn: async () => (await api.get(endpoint)).data,
    staleTime: 60_000,
  });
  const [selected, setSelected] = useState(null);

  if (isLoading || !data) {
    return <div className="text-white/40 text-sm text-center py-6">Cargando insignias…</div>;
  }

  const s = data.stats;
  const total = data.earned.length + data.locked.length;

  return (
    <div className="flex flex-col gap-4" data-testid="badges-panel">
      {/* Stats row */}
      <div className="grid grid-cols-4 gap-2">
        <StatCard icon={Flame} value={s.day_streak} label="días seguidos" color="text-orange-400" />
        <StatCard icon={Calendar} value={s.week_streak} label="semanas seguidas" color="text-qv-secondary" />
        <StatCard icon={Trophy} value={s.total_events} label="fiestas" color="text-yellow-300" />
        <StatCard icon={Star} value={s.genres_count} label="géneros" color="text-fuchsia-300" />
      </div>

      <div className="flex items-baseline justify-between px-1">
        <h3 className="font-display text-lg font-bold text-white">Insignias</h3>
        <span className="text-white/40 text-xs">{data.earned.length} / {total}</span>
      </div>

      <div className="grid grid-cols-4 gap-2">
        {data.earned.map((b) => (
          <motion.div key={b.id} initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
            <BadgeTile badge={b} earned onClick={() => setSelected(b)} />
          </motion.div>
        ))}
        {data.locked.map((b) => (
          <BadgeTile key={b.id} badge={b} earned={false} onClick={() => setSelected(b)} />
        ))}
      </div>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="bg-[#121215] border-white/10 text-white max-w-xs rounded-2xl">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <span className="text-2xl">{selected.emoji}</span>
                  {selected.name}
                </DialogTitle>
              </DialogHeader>
              <p className="text-white/70 text-sm">{selected.desc}</p>
              <p className="text-xs text-white/40 mt-2 capitalize">Categoría · {selected.tier}</p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
