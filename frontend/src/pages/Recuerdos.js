import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import api, { mediaThumb, mediaUrl } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import {
  CalendarDays, ArrowLeft, Play, Images, MapPin, ChevronLeft, ChevronRight,
  Loader2, Zap, List, Calendar, ChevronRight as ChevRight, PartyPopper,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

const LOCALE_BY_LANG = { es: "es-ES", en: "en-GB", de: "de-DE" };
const dateLocale = () => LOCALE_BY_LANG[(i18n.language || "es").slice(0, 2)] || "es-ES";

function formatDay(iso) {
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(dateLocale(), { weekday: "long", day: "numeric", month: "long" });
  } catch { return iso; }
}
function fmtFull(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString(dateLocale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  } catch { return dateStr; }
}
function monthKey(dateStr) {
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString(dateLocale(), { month: "long", year: "numeric" });
  } catch { return ""; }
}

// ---------------- LISTA (past parties) ----------------
function ListaView() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["past-events"],
    queryFn: async () => (await api.get("/me/past-events")).data,
    staleTime: 60000,
  });
  const items = data?.items || [];
  const groups = [];
  let cur = null;
  items.forEach((it) => {
    const k = monthKey(it.date);
    if (k !== cur) { groups.push({ key: k, items: [] }); cur = k; }
    groups[groups.length - 1].items.push(it);
  });

  if (isLoading) return <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>;
  if (items.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 bg-white/[0.02] p-8 text-center mt-2 mx-4">
        <PartyPopper className="w-10 h-10 text-white/30 mx-auto mb-3" />
        <p className="text-white/60 text-sm font-semibold mb-1">{t("recuerdos.empty_title")}</p>
        <p className="text-white/40 text-xs mb-4">{t("recuerdos.empty_body")}</p>
        <button onClick={() => navigate("/feed")} className="h-10 px-5 rounded-full bg-qv-primary text-white font-bold text-sm active:scale-95">{t("recuerdos.see_plans")}</button>
      </div>
    );
  }
  return (
    <div className="space-y-6 pb-6 px-4">
      {groups.map((g) => (
        <div key={g.key}>
          <p className="text-white/40 text-[11px] uppercase tracking-widest font-bold mb-2 capitalize">{g.key}</p>
          <div className="space-y-2.5">
            {g.items.map((it, i) => (
              <motion.button
                key={it.id}
                data-testid={`past-party-${it.id}`}
                onClick={() => navigate(`/event/${it.id}`)}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: Math.min(i * 0.03, 0.2) }}
                className="w-full flex items-center gap-3 p-2 rounded-2xl bg-[#121215] border border-white/10 text-left active:scale-[0.99]"
              >
                <div className="w-16 h-16 rounded-xl overflow-hidden bg-black shrink-0">
                  {it.image_url ? (
                    <img src={mediaThumb(it.image_url, 200)} alt="" className="w-full h-full object-cover" loading="lazy" />
                  ) : (
                    <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] to-[#0a1a1f]" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-display font-bold text-white text-sm leading-tight line-clamp-1">{it.name}</p>
                  <p className="text-white/50 text-xs mt-0.5 flex items-center gap-1 capitalize"><Calendar className="w-3 h-3" /> {fmtFull(it.date)}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${it.my_status === "estuve" ? "bg-qv-secondary/20 text-qv-secondary" : "bg-qv-primary/20 text-qv-primary"}`}>
                      {it.my_status === "estuve" ? t("recuerdos.status_estuve") : t("recuerdos.status_fui")}
                    </span>
                    {it.my_photos > 0 && (
                      <span className="text-[10px] text-white/60 flex items-center gap-1"><Images className="w-3 h-3" /> {it.my_photos}</span>
                    )}
                  </div>
                </div>
                <ChevRight className="w-5 h-5 text-white/30 shrink-0" />
              </motion.button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------- CALENDARIO ----------------
function CalendarioView() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const MONTHS = t("recuerdos.months", { returnObjects: true });
  const DOW = t("recuerdos.dow", { returnObjects: true });
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

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

  const grid = useMemo(() => {
    const first = new Date(year, month, 1);
    const last = new Date(year, month + 1, 0);
    const cells = [];
    const startDOW = (first.getDay() + 6) % 7;
    for (let i = 0; i < startDOW; i++) cells.push(null);
    for (let d = 1; d <= last.getDate(); d++) {
      const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      cells.push({ day: d, iso, data: daysMap[iso] });
    }
    return cells;
  }, [year, month, daysMap]);

  const goPrev = () => { if (month === 0) { setMonth(11); setYear((y) => y - 1); } else setMonth((m) => m - 1); };
  const goNext = () => { if (month === 11) { setMonth(0); setYear((y) => y + 1); } else setMonth((m) => m + 1); };

  return (
    <>
      <div className="flex items-center justify-between px-5 mb-3" data-testid="memories-month-nav">
        <button onClick={goPrev} data-testid="memories-prev" className="w-9 h-9 rounded-full bg-white/5 border border-white/15 flex items-center justify-center active:scale-90"><ChevronLeft className="w-5 h-5 text-white" /></button>
        <span className="font-display text-xl font-bold text-white capitalize">{MONTHS[month]} {year}</span>
        <button onClick={goNext} data-testid="memories-next" className="w-9 h-9 rounded-full bg-white/5 border border-white/15 flex items-center justify-center active:scale-90"><ChevronRight className="w-5 h-5 text-white" /></button>
      </div>
      <div className="px-5">
        <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-white/40 font-bold uppercase mb-1">
          {DOW.map((d, i) => <div key={i}>{d}</div>)}
        </div>
        <div className="grid grid-cols-7 gap-1 mb-6">
          {grid.map((cell, i) => {
            if (!cell) return <div key={i} className="aspect-square" />;
            const hasData = !!cell.data;
            return (
              <a key={cell.iso} href={`#day-${cell.iso}`} className={`aspect-square rounded-lg flex items-center justify-center text-sm font-bold ${hasData ? "bg-qv-primary/20 border border-qv-primary/40 text-white" : "text-white/25"}`}>
                {cell.day}
              </a>
            );
          })}
        </div>
      </div>
      {isLoading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 text-qv-primary animate-spin" /></div>
      ) : days.length === 0 ? (
        <p className="text-center text-white/40 py-10 px-6">{t("recuerdos.empty_month")}</p>
      ) : (
        <div className="px-4 flex flex-col gap-4 pb-8">
          {days.map((day) => (
            <div key={day.date} id={`day-${day.date}`} className="rounded-2xl border border-white/10 bg-white/[0.03] overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10 capitalize font-bold text-white">{formatDay(day.date)}</div>
              {day.events.map((ev) => {
                const media = [...(ev.photos || []), ...(ev.videos || [])];
                return (
                  <div key={ev.id} className="p-3">
                    <button onClick={() => navigate(`/event/${ev.id}`)} className="w-full flex items-center gap-3 mb-3 text-left active:scale-[0.99]">
                      {ev.image_url ? (
                        <img src={mediaThumb(ev.image_url, 160)} alt="" className="w-14 h-14 rounded-xl object-cover" />
                      ) : (
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-qv-primary to-qv-secondary" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="font-bold text-white truncate">{ev.name}</p>
                        <p className="text-white/50 text-xs flex items-center gap-1"><MapPin className="w-3 h-3" /> {ev.venue}</p>
                        {ev.friends?.length > 0 && (
                          <div className="flex -space-x-2 mt-1">
                            {ev.friends.slice(0, 5).map((f, i) => <AvatarCircle key={i} name={f.name} picture={f.picture} size={18} ring={false} />)}
                          </div>
                        )}
                      </div>
                    </button>
                    {(media.length > 0 || (ev.moments || []).length > 0) && (
                      <div className="grid grid-cols-4 gap-1">
                        {(ev.moments || []).map((m) => (
                          <div key={m.id} className="aspect-square rounded-lg overflow-hidden bg-black relative">
                            <img src={mediaThumb(m.image_url, 200)} alt="" className="w-full h-full object-cover" loading="lazy" />
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
                              <img src={mediaThumb(m.media_url, 200)} alt="" className="w-full h-full object-cover" loading="lazy" />
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
    </>
  );
}

/**
 * Recuerdos — unifica "Fiestas pasadas" (Lista) + "Calendario".
 */
export default function Recuerdos() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [view, setView] = useState("lista");

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} data-testid="recuerdos-back" className="w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center active:scale-90">
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <div>
          <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold flex items-center gap-1.5">
            <CalendarDays className="w-3.5 h-3.5" /> {t("recuerdos.eyebrow")}
          </p>
          <h1 className="font-display text-3xl font-black tracking-tighter">{t("recuerdos.title")}<span className="text-qv-primary">.</span></h1>
        </div>
      </header>

      {/* Toggle */}
      <div className="px-5 mb-4">
        <div className="flex gap-1.5 p-1 rounded-2xl bg-white/5 border border-white/10">
          <button
            data-testid="recuerdos-tab-lista"
            onClick={() => setView("lista")}
            className={`flex-1 py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors ${view === "lista" ? "bg-white text-black" : "text-white/60"}`}
          >
            <List className="w-3.5 h-3.5" /> {t("recuerdos.tab_list")}
          </button>
          <button
            data-testid="recuerdos-tab-calendario"
            onClick={() => setView("calendario")}
            className={`flex-1 py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors ${view === "calendario" ? "bg-white text-black" : "text-white/60"}`}
          >
            <Calendar className="w-3.5 h-3.5" /> {t("recuerdos.tab_calendar")}
          </button>
        </div>
      </div>

      {view === "lista" ? <ListaView /> : <CalendarioView />}
    </AppShell>
  );
}
