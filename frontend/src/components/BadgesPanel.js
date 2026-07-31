import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import api from "@/lib/api";
import { Lock, Flame, Calendar, Trophy, Star, Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const TIER_STYLES = {
  bronze: "from-amber-700 to-amber-500",
  silver: "from-slate-400 to-slate-200",
  gold: "from-yellow-400 to-amber-300",
  platinum: "from-fuchsia-400 to-qv-secondary",
};

const CATEGORY_LABEL = {
  asistencia: "Asistencia",
  racha: "Rachas",
  temporal: "Días especiales",
  social: "Social",
  referido: "Invita amigos",
  entrada: "Entradas",
  exploracion: "Exploración",
  captura: "Capturas & Stories",
  album: "Álbumes",
  otros: "Otros",
};

const CATEGORY_ORDER = [
  "asistencia", "racha", "temporal", "social", "referido",
  "entrada", "exploracion", "captura", "album", "otros",
];

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
      {badge.points && (
        <span className={`text-[9px] font-bold leading-none mt-0.5 ${earned ? "text-black/70" : "text-white/40"}`}>
          +{badge.points}
        </span>
      )}
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
  const [showAll, setShowAll] = useState(false);

  const grouped = useMemo(() => {
    if (!data) return null;
    const earnedIds = new Set(data.earned.map((b) => b.id));
    const all = [...data.earned, ...data.locked];
    const map = {};
    for (const b of all) {
      const cat = b.cat || "otros";
      map[cat] = map[cat] || { earned: [], locked: [] };
      if (earnedIds.has(b.id)) map[cat].earned.push(b);
      else map[cat].locked.push(b);
    }
    return map;
  }, [data]);

  if (isLoading || !data) {
    return <div className="text-white/40 text-sm text-center py-6">Cargando insignias…</div>;
  }

  const s = data.stats;
  const total = data.earned.length + data.locked.length;
  const pts = data.points || { total: 0, badge_points: 0, action_points: 0 };

  return (
    <div className="flex flex-col gap-4" data-testid="badges-panel">
      {/* Points hero */}
      <div className="rounded-2xl border border-yellow-300/30 bg-gradient-to-br from-yellow-300/15 via-transparent to-transparent p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-11 h-11 rounded-full bg-yellow-300/20 flex items-center justify-center">
              <Trophy className="w-6 h-6 text-yellow-300" />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest text-yellow-300 font-bold">Puntos totales</p>
              <p className="font-display text-3xl font-black text-white leading-none">{pts.total.toLocaleString("es-ES")}</p>
            </div>
          </div>
          <div className="text-right text-white/60 text-xs">
            <p>{pts.badge_points.toLocaleString("es-ES")} insignias</p>
            <p>{pts.action_points.toLocaleString("es-ES")} acciones</p>
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-2">
        <StatCard icon={Flame} value={s.day_streak} label="días" color="text-orange-400" />
        <StatCard icon={Calendar} value={s.week_streak} label="semanas" color="text-qv-secondary" />
        <StatCard icon={Trophy} value={s.total_events} label="fiestas" color="text-yellow-300" />
        <StatCard icon={Star} value={s.genres_count} label="géneros" color="text-fuchsia-300" />
      </div>

      <div className="flex items-baseline justify-between px-1">
        <h3 className="font-display text-lg font-bold text-white">Insignias</h3>
        <button
          data-testid="toggle-show-all"
          onClick={() => setShowAll((v) => !v)}
          className="text-white/50 text-xs font-bold hover:text-white"
        >
          {data.earned.length} / {total} · {showAll ? "Solo ganadas" : "Ver todas"}
        </button>
      </div>

      {CATEGORY_ORDER.map((cat) => {
        const g = grouped[cat];
        if (!g) return null;
        const items = showAll ? [...g.earned, ...g.locked] : g.earned;
        if (items.length === 0) return null;
        return (
          <div key={cat}>
            <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2 flex items-center gap-1.5">
              <Sparkles className="w-3 h-3 text-qv-secondary" /> {CATEGORY_LABEL[cat]}
              <span className="text-white/30 font-normal ml-auto">{g.earned.length}/{g.earned.length + g.locked.length}</span>
            </p>
            <div className="grid grid-cols-4 gap-2">
              {items.map((b) => (
                <motion.div key={b.id} initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
                  <BadgeTile
                    badge={b}
                    earned={g.earned.some((eb) => eb.id === b.id)}
                    onClick={() => setSelected(b)}
                  />
                </motion.div>
              ))}
            </div>
          </div>
        );
      })}

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
              <div className="flex items-center gap-2 mt-2 text-xs">
                <span className="capitalize px-2 py-0.5 rounded-full border border-white/15 text-white/70">
                  {selected.tier}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-yellow-300/20 text-yellow-200 font-bold">
                  +{selected.points} puntos
                </span>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
