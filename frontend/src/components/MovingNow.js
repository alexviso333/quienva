import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { TrendingUp, Flame, Eye } from "lucide-react";
import { mediaThumb } from "@/lib/api";

function movementScore(e) {
  return (e.total_going || 0) * 2
    + (e.total_interested || 0)
    + (e.signups_today || 0) * 3
    + (((e.friends_going || []).length) + ((e.friends_interested || []).length)) * 4;
}

// Only surface events with meaningful aggregated activity (avoids weak
// single-RSVP "social proof"). Real popular nights clear this easily.
const MIN_MOVEMENT = 4;

// Feed section: events with the most real activity right now, to create FOMO.
// Pure client-side from the events the feed already loaded. Hidden when there is
// no real activity (we never fabricate numbers). (Spec 4.1)
export default function MovingNow({ events, todayStr }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const hot = useMemo(() => {
    const list = (events || []).filter((e) => e.date >= todayStr && movementScore(e) >= MIN_MOVEMENT);
    list.sort((a, b) => movementScore(b) - movementScore(a) || (a.date || "").localeCompare(b.date || ""));
    return list.slice(0, 6);
  }, [events, todayStr]);

  if (hot.length < 1) return null;

  const activityLine = (e) => {
    const fg = (e.friends_going || []).length;
    if (fg > 0) return t("moving.friends_going", "{{count}} amigos van", { count: fg });
    const g = e.total_going || 0;
    const i = e.total_interested || 0;
    if (g + i >= 3) {
      if (g && i) return t("moving.going_interested", "{{g}} van · {{i}} interesados", { g, i });
      if (g) return t("moving.going_only", "{{g}} van", { g });
      return t("moving.interested_only", "{{i}} interesados", { i });
    }
    if ((e.signups_today || 0) > 0) return t("moving.signups_today", "{{count}} se han apuntado hoy", { count: e.signups_today });
    return t("moving.heating", "Se está calentando");
  };

  return (
    <section data-testid="feed-moving-now">
      <h2 className="text-lg font-black text-white flex items-center gap-2 font-display mb-3">
        <TrendingUp className="w-5 h-5 text-qv-secondary" /> {t("moving.title", "Se está moviendo")}
      </h2>
      <div className="flex gap-3 overflow-x-auto hide-scrollbar -mx-4 px-4 pb-1 snap-x">
        {hot.map((e) => (
          <button
            key={e.id}
            data-testid={`moving-event-${e.id}`}
            onClick={() => navigate(`/event/${e.id}`)}
            className="snap-start shrink-0 w-[150px] text-left active:scale-[0.98] transition-transform"
          >
            <div className="relative h-[190px] w-full rounded-2xl overflow-hidden bg-zinc-900 border border-white/10">
              {e.image_url ? (
                <img src={mediaThumb(e.image_url, 400)} alt={e.name} loading="lazy" className="w-full h-full object-cover" />
              ) : null}
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent" />
              <span className="absolute top-2 left-2 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full bg-black/50 backdrop-blur-sm text-qv-secondary border border-qv-secondary/30">
                <Flame className="w-3 h-3" /> {t("moving.badge", "Activo")}
              </span>
              <div className="absolute bottom-0 left-0 right-0 p-2.5">
                <p className="text-white font-bold text-sm leading-tight line-clamp-2">{e.name}</p>
                <p className="text-white/60 text-[11px] truncate mt-0.5">{e.venue}</p>
              </div>
            </div>
            <p className="mt-1.5 text-[11px] font-semibold text-qv-secondary flex items-center gap-1">
              <Eye className="w-3 h-3" /> {activityLine(e)}
            </p>
          </button>
        ))}
      </div>
    </section>
  );
}
