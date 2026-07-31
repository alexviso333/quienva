import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { CalendarDays, ArrowLeft, Play, Images, MapPin, ChevronLeft, ChevronRight, Loader2, Zap } from "lucide-react";

const MONTHS_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
const DOW_ES = ["L", "M", "X", "J", "V", "S", "D"];

function formatDay(iso) {
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  } catch { return iso; }
}

/**
 * Retrospective calendar — see your past parties + all shared multimedia by day.
 */
export default function Memories() {
  const navigate = useNavigate();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth()); // 0-indexed

  const start = useMemo(() => {
    const d = new Date(year, month, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
  }, [year, month]);
  const end = useMemo(() => {
    const d = new Date(year, month + 1, 0);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, [year, month]);

  const { data: days = [], isLoading } = useQuery({
    queryKey: ["memories", start, end],
    queryFn: async () => (await api.get(`/me/calendar?start=${start}&end=${end}`)).data,
  });

  const daysMap = useMemo(() => {
    const m = {};
    for (const d of days) m[d.date] = d;
    return m;
  }, [days]);

  // Build calendar grid (Mon-Sun)
  const grid = useMemo(() => {
    const first = new Date(year, month, 1);
    const last = new Date(year, month + 1, 0);
    const cells = [];
    const startDOW = (first.getDay() + 6) % 7; // Mon=0
    for (let i = 0; i < startDOW; i++) cells.push(null);
    for (let d = 1; d <= last.getDate(); d++) {
      const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      cells.push({ day: d, iso, data: daysMap[iso] });
    }
    return cells;
  }, [year, month, daysMap]);

  const goPrev = () => {
    if (month === 0) { setMonth(11); setYear(y => y - 1); }
    else setMonth(m => m - 1);
  };
  const goNext = () => {
    if (month === 11) { setMonth(0); setYear(y => y + 1); }
    else setMonth(m => m + 1);
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3 flex items-center gap-3">
        <button
          data-testid="memories-back"
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center active:scale-90"
        >
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <div>
          <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold flex items-center gap-1.5">
            <CalendarDays className="w-3.5 h-3.5" /> Recuerdos
          </p>
          <h1 className="font-display text-3xl font-black tracking-tighter">Calendario<span className="text-qv-primary">.</span></h1>
        </div>
      </header>

      {/* Month navigator */}
      <div className="flex items-center justify-between px-5 mb-3" data-testid="memories-month-nav">
        <button
          data-testid="memories-prev"
          onClick={goPrev}
          className="w-9 h-9 rounded-full bg-white/5 border border-white/15 flex items-center justify-center active:scale-90"
        >
          <ChevronLeft className="w-5 h-5 text-white" />
        </button>
        <span className="font-display text-xl font-bold text-white capitalize">
          {MONTHS_ES[month]} {year}
        </span>
        <button
          data-testid="memories-next"
          onClick={goNext}
          className="w-9 h-9 rounded-full bg-white/5 border border-white/15 flex items-center justify-center active:scale-90"
        >
          <ChevronRight className="w-5 h-5 text-white" />
        </button>
      </div>

      {/* Calendar grid */}
      <div className="px-5">
        <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-white/40 font-bold uppercase mb-1">
          {DOW_ES.map((d) => <div key={d}>{d}</div>)}
        </div>
        <div className="grid grid-cols-7 gap-1 mb-6">
          {grid.map((cell, i) => {
            if (!cell) return <div key={i} className="aspect-square" />;
            const hasData = !!cell.data;
            return (
              <a
                key={cell.iso}
                href={`#day-${cell.iso}`}
                data-testid={`memories-cell-${cell.iso}`}
                className={`aspect-square rounded-lg flex items-center justify-center text-sm font-bold ${
                  hasData
                    ? "bg-qv-primary/20 border border-qv-primary/40 text-white"
                    : "text-white/25"
                }`}
              >
                {cell.day}
              </a>
            );
          })}
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 text-qv-primary animate-spin" /></div>
      ) : days.length === 0 ? (
        <p className="text-center text-white/40 py-16 px-6">Sin fiestas en este mes. Marca &apos;Voy&apos; a un plan para empezar.</p>
      ) : (
        <div className="px-4 flex flex-col gap-4 pb-8" data-testid="memories-days">
          {days.map((day) => (
            <div key={day.date} id={`day-${day.date}`} className="rounded-2xl border border-white/10 bg-white/[0.03] overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10 capitalize font-bold text-white">
                {formatDay(day.date)}
              </div>
              {day.events.map((ev) => {
                const media = [...(ev.photos || []), ...(ev.videos || [])];
                return (
                  <div key={ev.id} className="p-3">
                    <button
                      onClick={() => navigate(`/event/${ev.id}`)}
                      className="w-full flex items-center gap-3 mb-3 text-left active:scale-[0.99]"
                    >
                      {ev.image_url ? (
                        <img src={mediaUrl(ev.image_url)} alt="" className="w-14 h-14 rounded-xl object-cover" />
                      ) : (
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-qv-primary to-qv-secondary" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="font-bold text-white truncate">{ev.name}</p>
                        <p className="text-white/50 text-xs flex items-center gap-1"><MapPin className="w-3 h-3" /> {ev.venue}</p>
                        {ev.friends?.length > 0 && (
                          <div className="flex -space-x-2 mt-1">
                            {ev.friends.slice(0, 5).map((f, i) => (
                              <AvatarCircle key={i} name={f.name} picture={f.picture} size={18} ring={false} />
                            ))}
                            {ev.friends.length > 5 && (
                              <span className="w-[18px] h-[18px] rounded-full bg-white/10 text-white/70 text-[9px] font-bold flex items-center justify-center border border-black">+{ev.friends.length - 5}</span>
                            )}
                          </div>
                        )}
                      </div>
                    </button>
                    {(media.length > 0 || (ev.moments || []).length > 0) && (
                      <div className="grid grid-cols-4 gap-1" data-testid={`memories-media-${ev.id}`}>
                        {(ev.moments || []).map((m) => (
                          <div key={m.id} className="aspect-square rounded-lg overflow-hidden bg-black relative">
                            <img src={mediaUrl(m.image_url)} alt="" className="w-full h-full object-cover" loading="lazy" />
                            <Zap className="absolute top-1 right-1 w-3 h-3 text-yellow-300" />
                          </div>
                        ))}
                        {media.map((m) => (
                          <div key={m.id} className="aspect-square rounded-lg overflow-hidden bg-black relative">
                            {m.media_type === "video" ? (
                              <>
                                <video src={mediaUrl(m.media_url)} muted playsInline preload="metadata" className="w-full h-full object-cover" />
                                <Play className="absolute inset-0 m-auto w-5 h-5 text-white drop-shadow" fill="white" />
                              </>
                            ) : (
                              <img src={mediaUrl(m.media_url)} alt="" className="w-full h-full object-cover" loading="lazy" />
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
