import { useState, useRef, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { EventCarousel } from "@/components/EventCarousel";
import { StoriesBar } from "@/components/Stories";
import { StreakBanner } from "@/components/StreakBanner";
import { FriendsActivity, RecapCard } from "@/components/FeedExtras";
import { AvatarCircle } from "@/components/AvatarCircle";
import FeedPlans, { FeedPlansControls } from "@/components/FeedPlans";
import FeedVenuesTonight from "@/components/FeedVenuesTonight";
import { useAuth } from "@/context/AuthContext";
import { useCompactMode } from "@/hooks/useCompactMode";
import InstallPwaBanner from "@/components/InstallPwaBanner";
import { Loader2, PartyPopper, Flame, ChevronRight, Users, Sparkles, Building2, Compass } from "lucide-react";
import { toast } from "sonner";

export default function Feed() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [genre, setGenre] = useState("all");
  const [view, setView] = useState("dia");
  const [sale, setSale] = useState("all");
  const [highlightId, setHighlightId] = useState(null);
  const [compact] = useCompactMode();
  const cardRefs = useRef({});

  // Curated carousels only decorate the default "Día" view (no genre filter).
  const isDefaultView = view === "dia" && genre === "all";
  // City is part of every event-related cache key: switching cities in Ajustes
  // must instantly swap to that city's cache (and refetch) instead of showing
  // the previous city's parties while a slow background refetch runs.
  const cityKey = user?.city || "-";

  const { data: topEvent } = useQuery({
    queryKey: ["top-weekend", cityKey],
    queryFn: async () => (await api.get("/events/top-weekend")).data,
    staleTime: 60_000,
  });

  const { data: carousels } = useQuery({
    queryKey: ["carousels", cityKey],
    queryFn: async () => (await api.get("/events/carousels")).data,
    enabled: isDefaultView,
    staleTime: 60_000,
  });

  const { data: genres = [] } = useQuery({
    queryKey: ["genres", cityKey],
    queryFn: async () => (await api.get("/events/genres")).data,
    staleTime: 5 * 60_000,
  });

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", cityKey, "all", genre],
    queryFn: async () => (await api.get("/events", { params: { date_filter: "all", genre } })).data,
    staleTime: 30_000,
  });

  // Newcomers with no friends yet: gently push them to Descubrir once, and keep
  // a persistent banner so "guiris" can find people/plans without any friends.
  const { data: friendsList } = useQuery({
    queryKey: ["friends"],
    queryFn: async () => (await api.get("/friends")).data,
    staleTime: 60_000,
  });
  const noFriends = Array.isArray(friendsList) && friendsList.length === 0;

  useEffect(() => {
    if (!noFriends) return;
    try {
      if (!localStorage.getItem("qv_discover_seen")) {
        localStorage.setItem("qv_discover_seen", "1");
        navigate("/descubrir");
      }
    } catch { /* ignore */ }
  }, [noFriends, navigate]);

  const setStatus = useMutation({
    mutationFn: async ({ eventId, status }) => (await api.post(`/events/${eventId}/interest`, { status })).data,
    // Optimistic: flip my_status instantly across every cached list (no lag).
    onMutate: async ({ eventId, status }) => {
      await qc.cancelQueries({ queryKey: ["events"] });
      const patchArr = (arr) =>
        Array.isArray(arr) ? arr.map((e) => (e.id === eventId ? { ...e, my_status: status } : e)) : arr;
      qc.getQueriesData({ queryKey: ["events"] }).forEach(([key, data]) => {
        qc.setQueryData(key, patchArr(data));
      });
      qc.setQueryData(["carousels"], (c) =>
        c
          ? {
              ...c,
              top_weekend: patchArr(c.top_weekend),
              friends_going: patchArr(c.friends_going),
              discover_new: patchArr(c.discover_new),
            }
          : c
      );
    },
    onSuccess: (_data, vars) => {
      if (vars.status === "voy") toast.success("¡Apuntado! Tus amigos ya lo verán 🎉");
      if (vars.status === "estuve") toast.success("Guardado en tus recuerdos ✨");
    },
    onError: () => {
      toast.error("No se pudo actualizar");
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["top-weekend"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
    },
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
     
  }, [events]);

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">
              {user?.city || "Palma de Mallorca"}
            </p>
            <h1 className="font-display text-4xl font-black tracking-tighter mt-1">
              Los planes<span className="text-qv-primary">.</span>
            </h1>
          </div>
          <button
            onClick={() => navigate("/locales")}
            className="mt-1 flex-shrink-0 flex items-center gap-1.5 text-xs font-bold text-white bg-white/10 border border-white/10 rounded-full px-3 py-2 active:scale-95"
            data-testid="feed-locales-btn"
          >
            <Building2 className="w-4 h-4 text-qv-secondary" /> Locales
          </button>
        </div>
      </header>

      <StoriesBar />

      <InstallPwaBanner />

      {noFriends && (
        <div className="px-4 pt-1 pb-1">
          <button
            data-testid="feed-descubrir-banner"
            onClick={() => navigate("/descubrir")}
            className="w-full rounded-2xl border border-qv-secondary/40 bg-gradient-to-r from-qv-primary/15 to-qv-secondary/15 p-3 flex items-center gap-3 text-left active:scale-[0.99]"
          >
            <div className="w-10 h-10 rounded-full bg-qv-secondary/20 flex items-center justify-center shrink-0">
              <Compass className="w-5 h-5 text-qv-secondary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display font-black text-white text-sm leading-tight">¿Nuevo por aquí? 👋</p>
              <p className="text-white/60 text-xs">Descubre gente y momentos para no salir solo.</p>
            </div>
            <ChevronRight className="w-5 h-5 text-white/40 shrink-0" />
          </button>
        </div>
      )}

      <FriendsActivity />

      <div className="px-4 pb-3">
        <StreakBanner />
      </div>

      <RecapCard />

      <div className="px-4 pb-3">
        <FeedPlansControls
          view={view}
          setView={setView}
          sale={sale}
          setSale={setSale}
          genres={genres}
          genre={genre}
          setGenre={setGenre}
        />
      </div>

      <div className="flex flex-col gap-4 px-4 pt-1">
        {!isDefaultView && topEvent && (topEvent.friends_going || []).length > 0 && (
          <button
            data-testid="top-weekend-banner"
            onClick={() => navigate(`/event/${topEvent.id}`)}
            className="relative w-full text-left rounded-2xl overflow-hidden border border-qv-primary/40 bg-[#1a0a12] active:scale-[0.99] transition-transform"
          >
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_left,_rgba(255,0,85,0.25),transparent_60%)]" />
            <div className="relative flex items-center gap-3 p-3">
              {topEvent.image_url && (
                <img src={mediaThumb(topEvent.image_url, 200)} alt={topEvent.name} className="w-16 h-16 rounded-xl object-cover shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold text-qv-primary">
                  <Flame className="w-3.5 h-3.5" /> Top del finde
                </p>
                <p className="font-display font-bold text-white truncate mt-0.5">{topEvent.name}</p>
                <div className="flex items-center gap-1.5 mt-1">
                  <div className="flex -space-x-2">
                    {topEvent.friends_going.slice(0, 3).map((f, i) => (
                      <AvatarCircle key={f.user_id + i} name={f.name} picture={f.picture} size={22} />
                    ))}
                  </div>
                  <span className="text-xs text-white/80 font-semibold">
                    {topEvent.friends_going.length} amigo{topEvent.friends_going.length > 1 ? "s" : ""} {topEvent.friends_going.length > 1 ? "van" : "va"}
                  </span>
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-white/40 shrink-0" />
            </div>
          </button>
        )}

        {isLoading ? (
          <div className="flex flex-col gap-4" data-testid="feed-skeleton">
            {[0, 1, 2].map((k) => (
              <div key={k} className="rounded-2xl overflow-hidden bg-[#121215] border border-white/10">
                <div className="h-40 bg-white/[0.06] animate-pulse" />
                <div className="p-3 flex flex-col gap-2.5">
                  <div className="h-8 w-2/3 bg-white/[0.06] rounded animate-pulse" />
                  <div className="grid grid-cols-2 gap-2">
                    <div className="h-10 bg-white/[0.06] rounded-xl animate-pulse" />
                    <div className="h-10 bg-white/[0.06] rounded-xl animate-pulse" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : events && events.length > 0 ? (
          <FeedPlans
            events={events}
            compact={compact}
            highlightId={highlightId}
            cardRefs={cardRefs}
            pending={false}
            onSetStatus={(eventId, status) => setStatus.mutate({ eventId, status })}
            view={view}
            sale={sale}
          />
        ) : (
          <div className="text-center py-20 px-6" data-testid="feed-empty">
            <PartyPopper className="w-12 h-12 text-white/30 mx-auto mb-4" />
            <p className="text-white/60">No hay planes ahora mismo.</p>
            <p className="text-white/40 text-sm mt-1">Vuelve pronto o revisa otros géneros.</p>
          </div>
        )}

        {/* Recurring free / non-ticketed plans open tonight — separate but visible */}
        <div className="-mx-4">
          <FeedVenuesTonight />
        </div>

        {/* Curated carousels — below the main list so the parties come first */}
        {isDefaultView && carousels && (
          <div className="-mx-4 pt-2">
            <EventCarousel
              testId="carousel-top-weekend"
              title="Top del finde"
              subtitle="Los planes con más movida"
              icon={Flame}
              events={carousels.top_weekend}
            />
            <EventCarousel
              testId="carousel-friends-going"
              title="Lo que va tu grupo"
              subtitle="Donde están tus amigos"
              icon={Users}
              events={carousels.friends_going}
            />
            <EventCarousel
              testId="carousel-discover-new"
              title="Prueba algo nuevo"
              subtitle="Géneros que aún no exploras"
              icon={Sparkles}
              events={carousels.discover_new}
            />
          </div>
        )}
      </div>
    </AppShell>
  );
}
