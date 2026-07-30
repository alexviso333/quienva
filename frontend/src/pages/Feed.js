import { useState } from "react";
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
];

export default function Feed() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [dateFilter, setDateFilter] = useState("all");
  const [genre, setGenre] = useState("all");

  const { data: genres = [] } = useQuery({
    queryKey: ["genres"],
    queryFn: async () => (await api.get("/events/genres")).data,
  });

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", dateFilter, genre],
    queryFn: async () =>
      (await api.get("/events", { params: { date_filter: dateFilter, genre } })).data,
  });

  const setStatus = useMutation({
    mutationFn: async ({ eventId, status }) =>
      (await api.post(`/events/${eventId}/interest`, { status })).data,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["events"] });
      if (vars.status === "voy") toast.success("¡Apuntado! Tus amigos ya lo verán 🎉");
    },
    onError: () => toast.error("No se pudo actualizar"),
  });

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4">
        <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">
          {user?.city || "Palma de Mallorca"}
        </p>
        <h1 className="font-display text-4xl font-black tracking-tighter mt-1">
          Los planes<span className="text-qv-primary">.</span>
        </h1>
      </header>

      {/* Filters */}
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

      {genres.length > 0 && (
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

      <div className="flex flex-col gap-6 px-4 pt-2">
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
              pending={setStatus.isPending}
              onSetStatus={(eventId, status) => setStatus.mutate({ eventId, status })}
            />
          ))
        ) : (
          <div className="text-center py-20 px-6" data-testid="feed-empty">
            <PartyPopper className="w-12 h-12 text-white/30 mx-auto mb-4" />
            <p className="text-white/60">No hay planes con estos filtros.</p>
            <p className="text-white/40 text-sm mt-1">Prueba a cambiar la fecha o el género.</p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
