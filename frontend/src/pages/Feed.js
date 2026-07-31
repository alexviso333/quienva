import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { EventCard } from "@/components/EventCard";
import { useAuth } from "@/context/AuthContext";
import { Loader2, PartyPopper } from "lucide-react";
import { toast } from "sonner";

const DATE_FILTERS = [
  { key: "all", label: "Todos" },
  { key: "hoy", label: "Hoy" },
  { key: "finde", label: "Este finde" },
  { key: "semana", label: "Próx. semana" },
  { key: "pasados", label: "Recuerdos" },
];

export default function Feed() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dateFilter, setDateFilter] = useState("all");
  const [genre, setGenre] = useState("all");
  const [highlightId, setHighlightId] = useState(null);
  const cardRefs = useRef({});

  const isPastView = dateFilter === "pasados";

  const { data: genres = [] } = useQuery({
    queryKey: ["genres"],
    queryFn: async () => (await api.get("/events/genres")).data,
  });

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", dateFilter, genre],
    queryFn: async () => (await api.get("/events", { params: { date_filter: dateFilter, genre } })).data,
  });

  const setStatus = useMutation({
    mutationFn: async ({ eventId, status }) => (await api.post(`/events/${eventId}/interest`, { status })).data,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["events"] });
      if (vars.status === "voy") toast.success("¡Apuntado! Tus amigos ya lo verán 🎉");
      if (vars.status === "estuve") toast.success("Guardado en tus recuerdos ✨");
    },
    onError: () => toast.error("No se pudo actualizar"),
  });

  // Deep-link: scroll to & highlight a shared event
  useEffect(() => {
    const target = searchParams.get("event");
    if (!target || !events) return;
    const found = events.find((e) => e.id === target);
    if (found) {
      setTimeout(() => {
        const el = cardRefs.current[target];
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
        setHighlightId(target);
        setTimeout(() => setHighlightId(null), 2600);
      }, 300);
      searchParams.delete("event");
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3">
        <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">
          {user?.city || "Palma de Mallorca"}
        </p>
        <h1 className="font-display text-4xl font-black tracking-tighter mt-1">
          {isPastView ? "Recuerdos" : "Los planes"}<span className="text-qv-primary">.</span>
        </h1>
      </header>

      <div className="flex overflow-x-auto hide-scrollbar gap-2 px-5 pb-2" data-testid="date-filters">
        {DATE_FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`filter-date-${f.key}`}
            onClick={() => setDateFilter(f.key)}
            className={`rounded-full px-5 py-2 text-sm font-semibold whitespace-nowrap transition-colors duration-300 ${
              dateFilter === f.key ? "bg-white text-black" : "bg-white/5 border border-white/10 text-white/70"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {genres.length > 0 && !isPastView && (
        <div className="flex overflow-x-auto hide-scrollbar gap-2 px-5 pb-4" data-testid="genre-filters">
          <button
            data-testid="filter-genre-all"
            onClick={() => setGenre("all")}
            className={`rounded-full px-4 py-1.5 text-xs font-semibold whitespace-nowrap transition-colors duration-300 ${
              genre === "all" ? "bg-qv-secondary text-black" : "bg-white/5 border border-white/10 text-white/60"
            }`}
          >
            Todo
          </button>
          {genres.map((g) => (
            <button
              key={g}
              data-testid={`filter-genre-${g}`}
              onClick={() => setGenre(g)}
              className={`rounded-full px-4 py-1.5 text-xs font-semibold whitespace-nowrap transition-colors duration-300 ${
                genre === g ? "bg-qv-secondary text-black" : "bg-white/5 border border-white/10 text-white/60"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-4 px-4 pt-1">
        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-7 h-7 text-qv-primary animate-spin" />
          </div>
        ) : events && events.length > 0 ? (
          events.map((ev, i) => (
            <EventCard
              key={ev.id}
              event={ev}
              index={i}
              highlight={highlightId === ev.id}
              cardRef={(el) => (cardRefs.current[ev.id] = el)}
              pending={setStatus.isPending}
              onSetStatus={(eventId, status) => setStatus.mutate({ eventId, status })}
            />
          ))
        ) : (
          <div className="text-center py-20 px-6" data-testid="feed-empty">
            <PartyPopper className="w-12 h-12 text-white/30 mx-auto mb-4" />
            <p className="text-white/60">
              {isPastView ? "Aún no hay recuerdos guardados." : "No hay planes con estos filtros."}
            </p>
            <p className="text-white/40 text-sm mt-1">
              {isPastView ? "Marca 'Estuve aquí' en eventos pasados." : "Prueba a cambiar la fecha o el género."}
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
