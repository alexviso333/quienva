import { useMemo, useState, useEffect, useRef } from "react";
import { EventCard } from "@/components/EventCard";
import { CompactEventCard } from "@/components/CompactEventCard";
import { CalendarDays, LayoutList, Building2, ChevronLeft, ChevronRight, PartyPopper, SlidersHorizontal, Euro } from "lucide-react";

const SALE_FILTERS = [
  { key: "all", label: "Todas" },
  { key: "a_la_venta", label: "🎟️ A la venta" },
  { key: "pocas_entradas", label: "⚡ Pocas" },
  { key: "agotado", label: "🔒 Agotadas" },
];

const VIEWS = [
  { key: "dia", label: "Día", icon: LayoutList },
  { key: "disco", label: "Discoteca", icon: Building2 },
  { key: "calendario", label: "Calendario", icon: CalendarDays },
];

const WD = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const WD_MINI = ["L", "M", "X", "J", "V", "S", "D"];
const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function isoToday() { return new Date().toISOString().slice(0, 10); }
function isoTomorrow() { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); }

function dayLabel(iso) {
  if (iso === isoToday()) return "Hoy";
  if (iso === isoTomorrow()) return "Mañana";
  const d = new Date(iso + "T00:00:00");
  const wd = WD[(d.getDay() + 6) % 7];
  return `${wd} ${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)}`;
}

export default function FeedPlans({ events, compact, onSetStatus, pending, highlightId, cardRefs, view = "dia", sale = "all" }) {
  const [monthCursor, setMonthCursor] = useState(() => { const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() }; });
  const [selDay, setSelDay] = useState(null);

  // Progressive rendering: mounting hundreds of cards at once is what makes the
  // feed feel slow, so we reveal cards in pages (by card count) as the user scrolls.
  const CARD_PAGE = 20;
  const [limit, setLimit] = useState(CARD_PAGE);
  const sentinelRef = useRef(null);
  useEffect(() => { setLimit(CARD_PAGE); }, [view, sale, events]);

  const shown = useMemo(() => {
    let list = events || [];
    if (sale !== "all") list = list.filter((e) => e.sale_state === sale);
    return list;
  }, [events, sale]);

  const byDay = useMemo(() => {
    const map = {};
    for (const e of shown) { (map[e.date] = map[e.date] || []).push(e); }
    return Object.keys(map).sort().map((d) => ({ date: d, items: map[d] }));
  }, [shown]);

  const byVenue = useMemo(() => {
    // Preserve the order venues first appear in the (already server-sorted) list
    // instead of sorting alphabetically. The backend floats our own events to the
    // top, so their venues naturally come first — with no visible marker.
    const map = {}; const order = [];
    for (const e of shown) {
      const v = e.venue || "Otros";
      if (!map[v]) { map[v] = []; order.push(v); }
      map[v].push(e);
    }
    return order.map((v) => ({
      venue: v, items: map[v].sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || ""))),
      // Admin-only: this club is one I carry via my link (any event marked).
      mine: map[v].some((e) => e.is_affiliate),
    }));
  }, [shown]);

  const daysWithEvents = useMemo(() => new Set(shown.map((e) => e.date)), [shown]);

  const renderCard = (ev, i) =>
    compact ? (
      <CompactEventCard
        key={ev.id}
        event={ev}
        index={i}
        onVoy={onSetStatus ? (status) => onSetStatus(ev.id, status) : undefined}
      />
    ) : (
      <EventCard
        key={ev.id}
        event={ev}
        index={i}
        highlight={highlightId === ev.id}
        cardRef={(el) => cardRefs && (cardRefs.current[ev.id] = el)}
        pending={pending}
        onSetStatus={onSetStatus}
      />
    );

  // Build calendar grid for the current month cursor
  const calCells = useMemo(() => {
    const { y, m } = monthCursor;
    const first = new Date(y, m, 1);
    const startPad = (first.getDay() + 6) % 7; // Mon-first
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < startPad; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      cells.push({ d, iso, has: daysWithEvents.has(iso) });
    }
    return cells;
  }, [monthCursor, daysWithEvents]);

  const selDayEvents = selDay ? shown.filter((e) => e.date === selDay) : [];

  const activeGroups = useMemo(
    () => (view === "dia" ? byDay : view === "disco" ? byVenue : []),
    [view, byDay, byVenue]
  );
  const shownGroups = useMemo(() => {
    const out = []; let n = 0;
    for (const g of activeGroups) { if (n >= limit) break; out.push(g); n += g.items.length; }
    return out;
  }, [activeGroups, limit]);
  const hasMore = shownGroups.length < activeGroups.length;
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore) return;
    const io = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) setLimit((l) => l + CARD_PAGE); },
      { rootMargin: "800px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, view]);

  return (
    <div className="flex flex-col gap-3">
      {shown.length === 0 && (
        <div className="text-center py-16 px-6" data-testid="feed-empty">
          <PartyPopper className="w-12 h-12 text-white/30 mx-auto mb-4" />
          <p className="text-white/60">No hay planes con estos filtros.</p>
        </div>
      )}

      {/* DÍA */}
      {view === "dia" && shownGroups.map((g) => (
        <div key={g.date} className="flex flex-col gap-3">
          <div className="flex items-center gap-2 pt-1">
            <span className="text-qv-primary font-display font-black text-lg">{dayLabel(g.date)}</span>
            <span className="text-white/30 text-xs">{g.items.length} {g.items.length === 1 ? "plan" : "planes"}</span>
            <div className="flex-1 h-px bg-white/10" />
          </div>
          {compact ? <div className="grid grid-cols-2 gap-3">{g.items.map(renderCard)}</div> : g.items.map(renderCard)}
        </div>
      ))}

      {/* DISCOTECA */}
      {view === "disco" && shownGroups.map((g) => (
        <div key={g.venue} className="flex flex-col gap-3">
          {g.mine ? (
            // Admin-only: club I carry via my link → highlighted header frame.
            // (is_affiliate is null for normal users, so g.mine is always false for them.)
            <div className="flex items-center gap-2 pt-1 rounded-xl border border-lime-400/70 bg-lime-400/10 px-2.5 py-1.5 shadow-[0_0_12px_rgba(132,204,22,0.35)]">
              <Building2 className="w-4 h-4 text-lime-300" />
              <span className="text-white font-display font-black text-lg truncate">{g.venue}</span>
              <span className="bg-gradient-to-r from-lime-300 to-green-500 text-black text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded-full flex items-center gap-0.5">
                <Euro className="w-2.5 h-2.5" /> Mi link
              </span>
              <span className="text-white/40 text-xs ml-auto">{g.items.length}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 pt-1">
              <Building2 className="w-4 h-4 text-qv-secondary" />
              <span className="text-white font-display font-black text-lg truncate">{g.venue}</span>
              <span className="text-white/30 text-xs">{g.items.length}</span>
              <div className="flex-1 h-px bg-white/10" />
            </div>
          )}
          {compact ? <div className="grid grid-cols-2 gap-3">{g.items.map(renderCard)}</div> : g.items.map(renderCard)}
        </div>
      ))}

      {/* CALENDARIO */}
      {view === "calendario" && (
        <div className="flex flex-col gap-3">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
            <div className="flex items-center justify-between mb-2">
              <button onClick={() => setMonthCursor((c) => { const m = c.m - 1; return m < 0 ? { y: c.y - 1, m: 11 } : { y: c.y, m }; })} className="p-1.5 rounded-lg bg-white/10 active:scale-95"><ChevronLeft className="w-4 h-4 text-white" /></button>
            <span className="font-display font-bold text-white capitalize">{MONTHS[monthCursor.m]} {monthCursor.y}</span>
              <button onClick={() => setMonthCursor((c) => { const m = c.m + 1; return m > 11 ? { y: c.y + 1, m: 0 } : { y: c.y, m }; })} className="p-1.5 rounded-lg bg-white/10 active:scale-95"><ChevronRight className="w-4 h-4 text-white" /></button>
            </div>
            <div className="grid grid-cols-7 gap-1 mb-1">
              {WD_MINI.map((d) => <div key={d} className="text-center text-[10px] text-white/40 font-bold">{d}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {calCells.map((c, i) => c === null ? <div key={i} /> : (
                <button
                  key={i}
                  onClick={() => c.has && setSelDay(c.iso)}
                  disabled={!c.has}
                  className={`aspect-square rounded-lg text-xs font-bold flex items-center justify-center relative ${
                    selDay === c.iso ? "bg-qv-primary text-black" : c.has ? "bg-qv-primary/20 text-white" : "text-white/25"
                  }`}
                >
                  {c.d}
                  {c.has && selDay !== c.iso && <span className="absolute bottom-1 w-1 h-1 rounded-full bg-qv-primary" />}
                </button>
              ))}
            </div>
          </div>
          {selDay ? (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span className="text-qv-primary font-display font-black text-lg">{dayLabel(selDay)}</span>
                <div className="flex-1 h-px bg-white/10" />
              </div>
              {selDayEvents.map(renderCard)}
            </div>
          ) : (
            <p className="text-white/40 text-sm text-center py-4">Toca un día con fiestas para verlas.</p>
          )}
        </div>
      )}

      {hasMore && (view === "dia" || view === "disco") && (
        <div ref={sentinelRef} className="flex justify-center py-6" data-testid="feed-load-more">
          <div className="w-6 h-6 rounded-full border-2 border-qv-primary/40 border-t-qv-primary animate-spin" />
        </div>
      )}
    </div>
  );
}

export function FeedPlansControls({ view, setView, sale, setSale, genres = [], genre = "all", setGenre }) {
  const [open, setOpen] = useState(false);
  const activeCount = (sale !== "all" ? 1 : 0) + (genre !== "all" ? 1 : 0);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="flex-1 grid grid-cols-3 gap-1.5 bg-white/[0.04] border border-white/10 rounded-2xl p-1" data-testid="feed-view-selector">
          {VIEWS.map((v) => {
            const Icon = v.icon;
            const on = view === v.key;
            return (
              <button
                key={v.key}
                onClick={() => setView(v.key)}
                data-testid={`view-${v.key}`}
                className={`flex items-center justify-center gap-1.5 rounded-xl py-2 text-xs font-bold transition-colors ${on ? "bg-qv-primary text-black" : "text-white/70"}`}
              >
                <Icon className="w-3.5 h-3.5" /> {v.label}
              </button>
            );
          })}
        </div>
        <button
          data-testid="feed-filtros-toggle"
          onClick={() => setOpen((o) => !o)}
          className={`relative shrink-0 h-[42px] px-3.5 rounded-2xl border flex items-center gap-1.5 text-xs font-bold transition-colors ${
            open || activeCount ? "bg-qv-secondary text-black border-qv-secondary" : "bg-white/[0.04] border-white/10 text-white/70"
          }`}
        >
          <SlidersHorizontal className="w-4 h-4" /> Filtros
          {activeCount > 0 && (
            <span className="ml-0.5 min-w-[16px] h-4 px-1 rounded-full bg-black/80 text-white text-[10px] font-black flex items-center justify-center">
              {activeCount}
            </span>
          )}
        </button>
      </div>

      {open && (
        <div className="flex flex-col gap-2 pt-1" data-testid="feed-filtros-panel">
          <div className="flex overflow-x-auto hide-scrollbar gap-2" data-testid="sale-filters">
            {SALE_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setSale(f.key)}
                data-testid={`filter-sale-${f.key}`}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold whitespace-nowrap ${sale === f.key ? "bg-qv-secondary text-black" : "bg-white/5 border border-white/10 text-white/60"}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          {genres.length > 0 && setGenre && (
            <div className="flex overflow-x-auto hide-scrollbar gap-2" data-testid="genre-filters">
              <button
                data-testid="filter-genre-all"
                onClick={() => setGenre("all")}
                className={`rounded-full px-4 py-1.5 text-xs font-semibold whitespace-nowrap ${genre === "all" ? "bg-qv-primary text-black" : "bg-white/5 border border-white/10 text-white/60"}`}
              >
                Todo
              </button>
              {genres.map((g) => (
                <button
                  key={g}
                  data-testid={`filter-genre-${g}`}
                  onClick={() => setGenre(g)}
                  className={`rounded-full px-4 py-1.5 text-xs font-semibold whitespace-nowrap ${genre === g ? "bg-qv-primary text-black" : "bg-white/5 border border-white/10 text-white/60"}`}
                >
                  {g}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

