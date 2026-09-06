import { useState, useRef, useEffect, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { EventCarousel } from "@/components/EventCarousel";
import { StoriesBar } from "@/components/Stories";
import { StreakBanner } from "@/components/StreakBanner";
import MontaGrupoBanner from "@/components/MontaGrupoBanner";
import { FriendsActivity, RecapCard } from "@/components/FeedExtras";
import { AvatarCircle } from "@/components/AvatarCircle";
import FeedPlans, { FeedPlansControls } from "@/components/FeedPlans";
import FeedVenuesTonight from "@/components/FeedVenuesTonight";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";
import { useCompactMode } from "@/hooks/useCompactMode";
import AppStorePromo from "@/components/AppStorePromo";
import MomentFeedBanner from "@/components/MomentFeedBanner";
import { isNativeApp } from "@/lib/platform";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { Loader2, PartyPopper, Flame, ChevronRight, Users, Sparkles, Building2, Compass, UserPlus, EyeOff, X, Camera, Search } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

export default function Feed() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { requireAuth } = useGuestGate();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [genre, setGenre] = useState("all");
  const [view, setView] = useState("dia");
  const [sale, setSale] = useState("all");
  const [q, setQ] = useState("");
  const [highlightId, setHighlightId] = useState(null);
  const [inviteFrom, setInviteFrom] = useState(null);
  const [showPrivacyReminder, setShowPrivacyReminder] = useState(false);
  const [guestCity, setGuestCity] = useState(() => {
    try { return localStorage.getItem("qv_guest_city") || "Palma de Mallorca"; } catch { return "Palma de Mallorca"; }
  });
  const [cities, setCities] = useState([{ id: "Palma de Mallorca", label: "Palma de Mallorca", emoji: "🏝️" }]);
  const [compact] = useCompactMode();
  const cardRefs = useRef({});

  // Curated carousels only decorate the default "Día" view (no genre filter).
  const isDefaultView = view === "dia" && genre === "all";
  // City is part of every event-related cache key: switching cities must instantly
  // swap to that city's cache (and refetch). Registered users use their account
  // city; guests can pick any supported city (?city= override) so visitors from
  // outside Palma still see their own scene.
  const effectiveCity = user?.city || guestCity;
  const cityParam = user ? undefined : guestCity;
  const cityKey = effectiveCity;

  // Load the supported-cities list so guests can switch city from the top bar.
  useEffect(() => {
    if (user) return;
    api.get("/cities").then(({ data }) => {
      if (data?.cities?.length) setCities(data.cities);
    }).catch(() => {});
  }, [user]);

  const pickCity = (c) => {
    setGuestCity(c);
    try { localStorage.setItem("qv_guest_city", c); } catch { /* ignore */ }
  };

  // Gentle one-time reminder for users who chose "Nadie" for their attendance
  // privacy, so they don't forget nobody can see where they're going.
  useEffect(() => {
    if (!user || user.attendance_privacy !== "nadie") { setShowPrivacyReminder(false); return; }
    try {
      if (localStorage.getItem(`qv_privacy_reminder_${user.user_id}`) !== "1") setShowPrivacyReminder(true);
    } catch { /* ignore */ }
  }, [user]);

  const dismissPrivacyReminder = () => {
    try { if (user) localStorage.setItem(`qv_privacy_reminder_${user.user_id}`, "1"); } catch { /* ignore */ }
    setShowPrivacyReminder(false);
  };

  const { data: topEvent } = useQuery({
    queryKey: ["top-weekend", cityKey],
    queryFn: async () => (await api.get("/events/top-weekend", { params: { city: cityParam } })).data,
    staleTime: 60_000,
  });

  const { data: carousels } = useQuery({
    queryKey: ["carousels", cityKey],
    queryFn: async () => (await api.get("/events/carousels", { params: { city: cityParam } })).data,
    enabled: isDefaultView,
    staleTime: 60_000,
  });

  const { data: genres = [] } = useQuery({
    queryKey: ["genres", cityKey],
    queryFn: async () => (await api.get("/events/genres", { params: { city: cityParam } })).data,
    staleTime: 5 * 60_000,
  });

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", cityKey, "all", genre],
    queryFn: async () => (await api.get("/events", { params: { date_filter: "all", genre, city: cityParam } })).data,
    staleTime: 30_000,
  });

  // Client-side search over the already-loaded events (party name, venue/club,
  // genre). Filtering locally keeps it instant AND avoids extra backend requests
  // (every network call counts toward Render's bandwidth budget).
  const qNorm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const isSearching = q.trim().length > 0;
  const filteredEvents = useMemo(() => {
    if (!events) return events;
    const tokens = qNorm(q).split(/\s+/).filter(Boolean);
    if (!tokens.length) return events;
    return events.filter((ev) => {
      const hay = qNorm(`${ev.name || ""} ${ev.venue || ""} ${ev.genre || ""} ${ev.address || ""}`);
      return tokens.every((tk) => hay.includes(tk));
    });
  }, [events, q]);

  // Newcomers with no friends yet: gently push them to Descubrir once, and keep
  // a persistent banner so "guiris" can find people/plans without any friends.
  const { data: friendsList } = useQuery({
    queryKey: ["friends"],
    queryFn: async () => (await api.get("/friends")).data,
    staleTime: 60_000,
  });
  const noFriends = Array.isArray(friendsList) && friendsList.length === 0;

  useEffect(() => {
    if (!user || !noFriends) return;
    try {
      if (!localStorage.getItem("qv_discover_seen")) {
        localStorage.setItem("qv_discover_seen", "1");
        navigate("/descubrir");
      }
    } catch { /* ignore */ }
  }, [noFriends, navigate, user]);

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
      toast.error(t("feed.toast_error"));
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["top-weekend"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
    },
  });

  // Invite landing (?add=username): a shared link drops guests straight on the
  // public feed. Guests see a banner and register to accept; logged-in users get
  // the friend request fired automatically. Either way the ?add param is cleaned
  // from the URL so it isn't re-applied on refresh.
  useEffect(() => {
    const add = searchParams.get("add");
    if (!add) return;
    const uname = add.toLowerCase().trim();
    searchParams.delete("add");
    setSearchParams(searchParams, { replace: true });
    if (!uname) return;
    if (user) {
      if (uname !== user.username) {
        api.post("/friends/request-by-username", { username: uname })
          .then(({ data }) => toast.success(
            data.status === "accepted" ? `¡Ya sois amigos con @${uname}! 🎉` : `Solicitud de amistad enviada a @${uname}`
          ))
          .catch(() => {});
      }
    } else {
      try { localStorage.setItem("qv_pending_add", uname); } catch { /* ignore */ }
      setInviteFrom(uname);
    }
     
  }, [searchParams, user]);

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
    <AppShell wide>
      <header className="px-5 pt-8 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold truncate">
              {user ? (user.city || "Palma de Mallorca") : ((cities.find((c) => c.id === guestCity) || {}).label || guestCity)}
            </p>
            <h1 className="font-display text-4xl lg:text-5xl font-black tracking-tighter mt-1">
              {t("feed.title")}<span className="text-qv-primary">.</span>
            </h1>
          </div>
          <button
            onClick={() => navigate("/locales")}
            className="mt-1 flex-shrink-0 flex items-center gap-1.5 text-xs font-bold text-white bg-white/10 border border-white/10 rounded-full px-3 py-2 active:scale-95"
            data-testid="feed-locales-btn"
          >
            <Building2 className="w-4 h-4 text-qv-secondary" /> {t("feed.locales")}
          </button>
        </div>
        {/* Language switcher — works for guests too (persists in localStorage,
            no session required). */}
        <div className="mt-3 flex justify-end">
          <LanguageSwitcher />
        </div>
      </header>

      {user && (
        <div className="px-5 -mt-1 mb-1">
          <button
            onClick={() => navigate("/momentos")}
            data-testid="feed-momentos-btn"
            className="flex items-center gap-1.5 text-xs font-bold text-white bg-qv-primary/15 border border-qv-primary/30 rounded-full px-3 py-2 active:scale-95"
          >
            <Camera className="w-4 h-4 text-qv-primary" /> Momentos
          </button>
        </div>
      )}


      {!user && (
        <div className="px-4 pt-1 pb-2" data-testid="guest-city-bar">
          <div className="flex flex-wrap items-center gap-2">
            {cities.map((c) => {
              const on = guestCity === c.id;
              const short = (c.label || c.id).split(",")[0].split(" de ")[0];
              return (
                <button
                  key={c.id}
                  data-testid={`city-chip-${c.id}`}
                  onClick={() => pickCity(c.id)}
                  className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold whitespace-nowrap border active:scale-95 transition-colors ${
                    on
                      ? "bg-qv-secondary text-black border-qv-secondary shadow-[0_0_14px_rgba(0,240,255,0.35)]"
                      : "bg-white/5 border-white/12 text-white/70"
                  }`}
                >
                  {c.emoji ? `${c.emoji} ` : ""}{short}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {user && <StoriesBar />}

      {user && <MomentFeedBanner />}

      {!isNativeApp() && <AppStorePromo />}

      {user && showPrivacyReminder && (
        <div className="px-4 pt-1 pb-1">
          <div
            data-testid="privacy-reminder"
            className="w-full rounded-2xl border border-white/12 bg-white/5 p-3 flex items-center gap-3"
          >
            <div className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center shrink-0">
              <EyeOff className="w-4 h-4 text-white/70" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-semibold leading-tight">{t("feed.hidden_mode_title")}</p>
              <p className="text-white/55 text-xs">{t("feed.hidden_mode_body")}</p>
            </div>
            <button
              onClick={() => { dismissPrivacyReminder(); navigate("/ajustes"); }}
              data-testid="privacy-reminder-settings"
              className="shrink-0 text-xs font-bold text-qv-secondary bg-qv-secondary/15 border border-qv-secondary/40 rounded-full px-3 py-1.5 active:scale-95"
            >
              {t("feed.settings")}
            </button>
            <button
              onClick={dismissPrivacyReminder}
              data-testid="privacy-reminder-dismiss"
              aria-label={t("feed.dismiss")}
              className="shrink-0 text-white/40 active:scale-90"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {!user && inviteFrom && (
        <div className="px-4 pt-1 pb-1">
          <div
            data-testid="feed-invite-banner"
            className="w-full rounded-2xl border border-qv-secondary/50 bg-gradient-to-r from-qv-secondary/15 to-qv-primary/15 p-3 flex items-center gap-3 text-left"
          >
            <div className="w-10 h-10 rounded-full bg-qv-secondary/20 flex items-center justify-center shrink-0">
              <UserPlus className="w-5 h-5 text-qv-secondary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display font-black text-white text-sm leading-tight">
                <span className="text-qv-secondary">@{inviteFrom}</span> {t("feed.invited_suffix")}
              </p>
              <p className="text-white/60 text-xs">{t("feed.invited_sub")}</p>
            </div>
            <button
              onClick={() => requireAuth(`aceptar la invitación de @${inviteFrom}`)}
              data-testid="feed-invite-accept"
              className="shrink-0 text-xs font-bold text-black bg-qv-secondary rounded-full px-4 py-2 active:scale-95"
            >
              {t("feed.accept")}
            </button>
          </div>
        </div>
      )}

      {!user && !inviteFrom && (
        <div className="px-4 pt-1 pb-1">
          <div
            data-testid="feed-guest-banner"
            className="w-full rounded-2xl border border-qv-primary/40 bg-gradient-to-r from-qv-primary/15 to-qv-secondary/15 p-3 flex items-center gap-3 text-left"
          >
            <div className="w-10 h-10 rounded-full bg-qv-primary/20 flex items-center justify-center shrink-0">
              <Sparkles className="w-5 h-5 text-qv-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display font-black text-white text-sm leading-tight">{t("feed.guest_title")}</p>
              <p className="text-white/60 text-xs">{t("feed.guest_sub")}</p>
            </div>
            <button
              onClick={() => requireAuth("empezar")}
              data-testid="feed-guest-register"
              className="shrink-0 text-xs font-bold text-white bg-qv-primary rounded-full px-4 py-2 active:scale-95"
            >
              {t("feed.enter")}
            </button>
          </div>
        </div>
      )}

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

      {user && <FriendsActivity />}

      <div className="px-4 pb-3">
        {user && <StreakBanner />}
      </div>

      {user && (
        <div className="px-4 pb-3">
          <MontaGrupoBanner />
        </div>
      )}

      {user && !isNativeApp() && <RecapCard />}

      <div className="px-4 pb-3">
        <div className="relative mb-3">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40 pointer-events-none" />
          <input
            data-testid="feed-search-input"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("feed.search_placeholder", "Busca fiesta, discoteca o estilo\u2026")}
            className="w-full h-11 rounded-2xl bg-white/5 border border-white/12 pl-10 pr-10 text-sm text-white placeholder-white/40 focus:outline-none focus:border-qv-primary/50 focus:bg-white/[0.07]"
          />
          {isSearching && (
            <button
              data-testid="feed-search-clear"
              onClick={() => setQ("")}
              aria-label={t("common.clear", "Borrar")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
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
            className="relative w-full lg:max-w-3xl text-left rounded-2xl overflow-hidden border border-qv-primary/40 bg-[#1a0a12] active:scale-[0.99] transition-transform"
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
                    {t("feed.friends_going", { count: topEvent.friends_going.length })}
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
        ) : events && filteredEvents && filteredEvents.length > 0 ? (
          <FeedPlans
            events={filteredEvents}
            compact={compact}
            highlightId={highlightId}
            cardRefs={cardRefs}
            pending={false}
            onSetStatus={(eventId, status) => {
              if (!requireAuth("apuntarte a los planes")) return;
              setStatus.mutate({ eventId, status });
            }}
            view={view}
            sale={sale}
          />
        ) : isSearching ? (
          <div className="text-center py-16 px-6" data-testid="feed-search-empty">
            <Search className="w-12 h-12 text-white/30 mx-auto mb-4" />
            <p className="text-white/60">{t("feed.search_empty_title", "Sin resultados para \u201c{{q}}\u201d", { q })}</p>
            <p className="text-white/40 text-sm mt-1">{t("feed.search_empty_body", "Prueba con otro nombre de fiesta, discoteca o estilo.")}</p>
          </div>
        ) : (
          <div className="text-center py-20 px-6" data-testid="feed-empty">
            <PartyPopper className="w-12 h-12 text-white/30 mx-auto mb-4" />
            <p className="text-white/60">{t("feed.empty_title")}</p>
            <p className="text-white/40 text-sm mt-1">{t("feed.empty_body")}</p>
          </div>
        )}

        {/* Recurring free / non-ticketed plans open tonight — separate but visible */}
        {!isSearching && (
        <div className="-mx-4">
          <FeedVenuesTonight />
        </div>
        )}

        {/* Curated carousels — below the main list so the parties come first */}
        {isDefaultView && !isSearching && carousels && (
          <div className="-mx-4 pt-2">
            <EventCarousel
              testId="carousel-top-weekend"
              title={t("feed.carousel_top_title")}
              subtitle={t("feed.carousel_top_subtitle")}
              icon={Flame}
              events={carousels.top_weekend}
            />
            {user && (
              <EventCarousel
                testId="carousel-friends-going"
                title={t("feed.carousel_friends_title")}
                subtitle={t("feed.carousel_friends_subtitle")}
                icon={Users}
                events={carousels.friends_going}
              />
            )}
            <EventCarousel
              testId="carousel-discover-new"
              title={t("feed.carousel_discover_title")}
              subtitle={t("feed.carousel_discover_subtitle")}
              icon={Sparkles}
              events={carousels.discover_new}
            />
          </div>
        )}
      </div>
    </AppShell>
  );
}
