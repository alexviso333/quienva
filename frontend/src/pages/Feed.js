import { useState, useRef, useEffect, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { EventCard } from "@/components/EventCard";
import { CompactEventCard } from "@/components/CompactEventCard";
import { StoriesBar } from "@/components/Stories";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";
import { isNativeApp } from "@/lib/platform";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import CitySelectorSheet from "@/components/CitySelectorSheet";
import MontaPlanBanner from "@/components/MontaPlanBanner";
import MyOpenPlans from "@/components/MyOpenPlans";
import MovingNow from "@/components/MovingNow";
import { captureEvent } from "@/analytics/posthog";
import { PartyPopper, Flame, ChevronRight, Users, Sparkles, Building2, Compass, UserPlus, EyeOff, X, Search, MapPin, ChevronDown, Moon, LayoutGrid, Rows3 } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

// ============================================================================
// SPRINT 1 — "TONIGHT": el Feed responde a UNA pregunta en 5s: ¿dónde está la
// noche esta noche y quién va? Se redujo de ~13 bloques a EXACTAMENTE 3:
//   A) 🔥 Esta noche   B) ⚡ Tu gente   C) 🌙 Próximamente
// Componentes RETIRADOS del render (conservados en el codebase por si se
// reactivan): EventCarousel, StreakBanner, MontaGrupoBanner, FriendsActivity,
// RecapCard, FeedPlans/FeedPlansControls, FeedVenuesTonight, AppStorePromo,
// MomentFeedBanner, y el auto-redirect a /descubrir.
// Se mantiene para TODAS las ciudades actuales (no se concentra en una).
// ============================================================================

const pad2 = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const WEEKDAYS_ES = ["domingo", "lunes", "martes", "mi\u00e9rcoles", "jueves", "viernes", "s\u00e1bado"];

// Actividad social combinada: "voy" + "me interesa" (afinado en Sprint 2 con
// contadores separados). Define el orden del Bloque A.
const socialScore = (e) => (e.total_going || 0) + (e.total_interested || 0);
const friendScore = (e) => (e.friends_going?.length || 0) + (e.friends_interested?.length || 0);

function SkeletonList() {
  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-2 lg:gap-4 xl:grid-cols-3" data-testid="feed-skeleton">
      {[0, 1, 2].map((k) => (
        <div key={k} className="rounded-[26px] overflow-hidden bg-[#121217] border border-white/10">
          <div className="h-44 qv-skeleton" />
          <div className="p-4 flex flex-col gap-3">
            <div className="h-7 w-2/3 qv-skeleton rounded-lg" />
            <div className="h-4 w-1/2 qv-skeleton rounded-md" />
            <div className="grid grid-cols-2 gap-2.5 mt-1">
              <div className="h-11 qv-skeleton rounded-xl" />
              <div className="h-11 qv-skeleton rounded-xl" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ icon: Icon, title, count, tint = "primary" }) {
  const tints = {
    primary: "text-qv-primary bg-qv-primary/15 border-qv-primary/30 shadow-[0_0_20px_-5px_rgba(255,0,85,0.7)]",
    secondary: "text-qv-secondary bg-qv-secondary/15 border-qv-secondary/30 shadow-[0_0_20px_-5px_rgba(0,240,255,0.7)]",
    muted: "text-white/80 bg-white/[0.08] border-white/15",
  };
  return (
    <motion.div
      className="flex items-center gap-3 mb-4"
      initial={{ opacity: 0, x: -14 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <motion.span
        className={`w-9 h-9 rounded-2xl border flex items-center justify-center ${tints[tint]}`}
        initial={{ scale: 0.6, opacity: 0 }}
        whileInView={{ scale: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ type: "spring", stiffness: 420, damping: 18, delay: 0.08 }}
      >
        <Icon className="w-[18px] h-[18px]" />
      </motion.span>
      <h2 className="font-display font-black text-[22px] leading-none tracking-[-0.01em] text-white">{title}</h2>
      {count != null && count > 0 && (
        <span className="text-[11px] font-bold text-white/80 bg-gradient-to-r from-qv-primary/25 to-qv-secondary/25 border border-white/10 rounded-full px-2.5 py-0.5">{count}</span>
      )}
      <div className="flex-1 h-px bg-gradient-to-r from-white/15 via-white/5 to-transparent" />
    </motion.div>
  );
}

export default function Feed() {
  const { t } = useTranslation();
  const { user, setUser } = useAuth();
  const { requireAuth } = useGuestGate();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState("");
  // Engagement signal: fire feed_scrolled once per mount when the user scrolls deep.
  useEffect(() => {
    let fired = false;
    const onScroll = () => {
      const depth = window.scrollY || document.documentElement.scrollTop || 0;
      if (!fired && depth > 700) {
        fired = true;
        captureEvent("feed_scrolled", { depth_px: Math.round(depth) });
        window.removeEventListener("scroll", onScroll);
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const [highlightId, setHighlightId] = useState(null);
  const [inviteFrom, setInviteFrom] = useState(null);
  const [showPrivacyReminder, setShowPrivacyReminder] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [guestCity, setGuestCity] = useState(() => {
    try { return localStorage.getItem("qv_guest_city") || "Palma de Mallorca"; } catch { return "Palma de Mallorca"; }
  });
  const [cities, setCities] = useState([{ id: "Palma de Mallorca", label: "Palma de Mallorca", emoji: "\ud83c\udfdd\ufe0f" }]);
  const [citySheetOpen, setCitySheetOpen] = useState(false);
  const [citySaving, setCitySaving] = useState(false);
  const cardRefs = useRef({});
  const sentinelRef = useRef(null);
  const [visibleUpcoming, setVisibleUpcoming] = useState(12);
  // "Modo compacto": 2 tarjetas por fila en móvil (persistido).
  const [compact, setCompact] = useState(() => {
    try { return localStorage.getItem("qv_compact") === "1"; } catch { return false; }
  });
  const toggleCompact = () => setCompact((c) => {
    const n = !c;
    try { localStorage.setItem("qv_compact", n ? "1" : "0"); } catch { /* ignore */ }
    return n;
  });

  // City is part of every event-related cache key: switching cities instantly
  // swaps to that city's cache. Registered users use their account city; guests
  // can pick any supported city (?city= override).
  const effectiveCity = user?.city || guestCity;
  const cityParam = user ? undefined : guestCity;
  const cityKey = effectiveCity;
  const cityLabel = user
    ? (user.city || "Palma de Mallorca")
    : ((cities.find((c) => c.id === guestCity) || {}).label || guestCity);

  // Keep the hero clock fresh (day/hour) without hammering anything.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  // Load the supported-cities list (for the picker + the guest top bar).
  useEffect(() => {
    api.get("/cities").then(({ data }) => {
      if (data?.cities?.length) setCities(data.cities);
    }).catch(() => {});
  }, []);

  const pickCity = (c) => {
    setGuestCity(c);
    try { localStorage.setItem("qv_guest_city", c); } catch { /* ignore */ }
  };

  // First launch on the installed app / right after social sign-up: offer to
  // confirm the city once (dismissible, never nags again).
  useEffect(() => {
    let forcePick = false;
    try { forcePick = localStorage.getItem("qv_pick_city") === "1"; } catch { /* ignore */ }
    if (forcePick) {
      try { localStorage.removeItem("qv_pick_city"); } catch { /* ignore */ }
      setCitySheetOpen(true);
      return;
    }
    if (!isNativeApp()) return;
    let seen = false;
    try { seen = localStorage.getItem("qv_city_gate_seen") === "1"; } catch { /* ignore */ }
    if (!seen) setCitySheetOpen(true);
  }, []);

  const markCityGateSeen = () => {
    try { localStorage.setItem("qv_city_gate_seen", "1"); } catch { /* ignore */ }
  };

  const closeCitySheet = () => {
    markCityGateSeen();
    setCitySheetOpen(false);
  };

  const handlePickCity = async (cityId) => {
    if (user) {
      if (cityId === user.city) { closeCitySheet(); return; }
      try {
        setCitySaving(true);
        const { data } = await api.put("/auth/profile", { city: cityId });
        setUser(data);
        try { localStorage.setItem("qv_user", JSON.stringify(data)); } catch { /* ignore */ }
        toast.success(`Tu ciudad ahora es ${(cities.find((c) => c.id === cityId) || {}).label || cityId}`);
      } catch {
        toast.error("No se pudo cambiar la ciudad");
      } finally {
        setCitySaving(false);
      }
    } else {
      pickCity(cityId);
    }
    markCityGateSeen();
    setCitySheetOpen(false);
  };

  // Gentle one-time reminder for users in "ghost" attendance mode.
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

  // All upcoming events for the active city (single source for the 3 blocks).
  const { data: events, isLoading } = useQuery({
    queryKey: ["events", cityKey, "all"],
    queryFn: async () => (await api.get("/events", { params: { date_filter: "all", city: cityParam } })).data,
    staleTime: 30_000,
  });

  // Friends list only to know whether to even consider the "Tu gente" block.
  const { data: friendsList } = useQuery({
    queryKey: ["friends"],
    queryFn: async () => (await api.get("/friends")).data,
    staleTime: 60_000,
    enabled: !!user,
  });
  const noFriends = !!user && Array.isArray(friendsList) && friendsList.length === 0;

  // Client-side search over the loaded events (name / venue / genre / address).
  const qNorm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const isSearching = q.trim().length > 0;
  const filteredEvents = useMemo(() => {
    if (!events) return [];
    const tokens = qNorm(q).split(/\s+/).filter(Boolean);
    if (!tokens.length) return events;
    return events.filter((ev) => {
      const hay = qNorm(`${ev.name || ""} ${ev.venue || ""} ${ev.genre || ""} ${ev.address || ""}`);
      return tokens.every((tk) => hay.includes(tk));
    });
  }, [events, q]);

  // ---- The 3 blocks -------------------------------------------------------
  const todayStr = isoDate(now);
  const { blockToday, blockFriends, blockUpcoming } = useMemo(() => {
    const list = events || [];

    // A) Esta noche: eventos de HOY, por actividad social, máx 5.
    const todayAll = list.filter((e) => e.date === todayStr);
    todayAll.sort((a, b) =>
      socialScore(b) - socialScore(a) ||
      (b.featured ? 1 : 0) - (a.featured ? 1 : 0) ||
      (a.time || "").localeCompare(b.time || "")
    );
    const blockToday = todayAll;
    const aIds = new Set(blockToday.map((e) => e.id));

    // B) Tu gente: eventos (cualquier día) con ≥1 amigo apuntado/interesado,
    //    excluyendo los ya mostrados en A para no duplicar tarjetas.
    let blockFriends = [];
    if (user) {
      const fr = list.filter((e) => !aIds.has(e.id) && friendScore(e) > 0);
      fr.sort((a, b) => friendScore(b) - friendScore(a) || a.date.localeCompare(b.date));
      blockFriends = fr.slice(0, 6);
    }
    const bIds = new Set(blockFriends.map((e) => e.id));

    // C) Próximamente: cualquier día futuro (no solo findes), excluyendo A y B.
    //    SIN tope — se renderiza de forma progresiva al hacer scroll.
    const up = list.filter((e) => e.date > todayStr && !aIds.has(e.id) && !bIds.has(e.id));
    up.sort((a, b) => a.date.localeCompare(b.date) || socialScore(b) - socialScore(a));
    const blockUpcoming = up;

    return { blockToday, blockFriends, blockUpcoming };
  }, [events, user, todayStr]);

  // Progressive rendering for the (potentially long) "Próximamente" list.
  const upcomingShown = blockUpcoming.slice(0, visibleUpcoming);
  const hasMoreUpcoming = upcomingShown.length < blockUpcoming.length;
  useEffect(() => { setVisibleUpcoming(12); }, [cityKey]);
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || isSearching || !hasMoreUpcoming) return;
    const io = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) setVisibleUpcoming((c) => c + 8); },
      { rootMargin: "700px" }
    );
    io.observe(el);
    return () => io.disconnect();
    // `visibleUpcoming` in deps: re-arm the observer after each page so it keeps
    // loading while the sentinel stays on-screen (avoids a stuck spinner).
  }, [hasMoreUpcoming, isSearching, visibleUpcoming]);

  // Apply an interest change to a cached event OPTIMISTICALLY: flips my_status
  // and adjusts going_count / interested_count instantly so the UI never waits
  // for the network (no spinner, no toast, no perceived lag).
  const applyStatus = (e, status) => {
    if (!e) return e;
    const prev = e.my_status;
    if (prev === status) return e;
    let gc = e.going_count ?? 0;
    let ic = e.interested_count ?? 0;
    if (prev === "voy") gc = Math.max(0, gc - 1);
    if (prev === "me_interesa") ic = Math.max(0, ic - 1);
    if (status === "voy") gc += 1;
    if (status === "me_interesa") ic += 1;
    return { ...e, my_status: status, going_count: gc, interested_count: ic };
  };

  const setStatus = useMutation({
    mutationFn: async ({ eventId, status }) => (await api.post(`/events/${eventId}/interest`, { status })).data,
    onMutate: async ({ eventId, status }) => {
      await qc.cancelQueries({ queryKey: ["events"] });
      const patchArr = (arr) =>
        Array.isArray(arr) ? arr.map((e) => (e.id === eventId ? applyStatus(e, status) : e)) : arr;
      qc.getQueriesData({ queryKey: ["events"] }).forEach(([key, data]) => {
        qc.setQueryData(key, patchArr(data));
      });
    },
    // No success toast on purpose: the optimistic update already reflects the
    // choice instantly, so a green toast would only highlight the round-trip.
    onError: () => {
      toast.error(t("feed.toast_error"));
      qc.invalidateQueries({ queryKey: ["events"] });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["events"] });
    },
  });

  // Invite landing (?add=username).
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
            data.status === "accepted" ? `\u00a1Ya sois amigos con @${uname}! \ud83c\udf89` : `Solicitud de amistad enviada a @${uname}`
          ))
          .catch(() => {});
      }
    } else {
      try { localStorage.setItem("qv_pending_add", uname); } catch { /* ignore */ }
      setInviteFrom(uname);
    }
     
  }, [searchParams, user]);

  // Deep-link: scroll to & highlight a shared event.
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

  const onSetStatus = (eventId, status) => {
    if (!requireAuth("apuntarte a los planes")) return;
    setStatus.mutate({ eventId, status });
  };

  const renderList = (arr) => (
    compact ? (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" data-testid="feed-grid-compact">
        {arr.map((ev, i) => (
          <CompactEventCard
            key={ev.id}
            event={ev}
            index={i}
            onVoy={(status) => onSetStatus(ev.id, status)}
          />
        ))}
      </div>
    ) : (
    <div className="flex flex-col gap-3 lg:grid lg:grid-cols-2 lg:gap-4 xl:grid-cols-3 lg:items-start">
      {arr.map((ev, i) => (
        <EventCard
          key={ev.id}
          event={ev}
          index={i}
          highlight={highlightId === ev.id}
          cardRef={(el) => cardRefs.current && (cardRefs.current[ev.id] = el)}
          pending={false}
          onSetStatus={onSetStatus}
        />
      ))}
    </div>
    )
  );

  const nothingTonight = !isLoading && blockToday.length === 0;

  return (
    <AppShell wide>
      <CitySelectorSheet
        open={citySheetOpen}
        cities={cities}
        currentCity={effectiveCity}
        onPick={handlePickCity}
        onClose={closeCitySheet}
        saving={citySaving}
      />

      {/* ---- HERO ---- */}
      <header className="relative px-5 pt-4 pb-1 lg:pt-7 lg:pb-2">
        {/* ambient neon glow */}
        <div aria-hidden className="qv-glow-a pointer-events-none absolute -top-16 -left-16 w-72 h-72 rounded-full bg-qv-primary/20 blur-[90px]" />
        <div aria-hidden className="qv-glow-b pointer-events-none absolute -top-10 right-0 w-64 h-64 rounded-full bg-qv-secondary/15 blur-[90px]" />
        <div className="relative">
          <div className="flex items-start justify-between gap-3">
            <button
              onClick={() => setCitySheetOpen(true)}
              data-testid="feed-city-switch-btn"
              className="group inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] backdrop-blur-md border border-qv-secondary/50 pl-2.5 pr-2.5 py-1.5 active:scale-95 transition-transform shadow-[0_0_24px_-6px_rgba(0,240,255,0.7)]"
            >
              <MapPin className="w-4 h-4 shrink-0 text-qv-secondary" />
              <span className="truncate max-w-[42vw] text-sm font-extrabold text-qv-secondary drop-shadow-[0_0_6px_rgba(0,240,255,0.6)]">
                {cityLabel}
              </span>
              <ChevronDown className="w-4 h-4 shrink-0 text-qv-secondary group-active:translate-y-0.5 transition-transform" />
            </button>
            <div className="flex items-center gap-2 shrink-0">
              <LanguageSwitcher compact />
              <button
                onClick={toggleCompact}
                aria-label={compact ? "Vista ampliada" : "Vista compacta"}
                data-testid="feed-compact-toggle"
                className="flex items-center justify-center w-9 h-9 text-white bg-white/[0.08] border border-white/10 rounded-full active:scale-95"
              >
                {compact ? <Rows3 className="w-4 h-4 text-qv-secondary" /> : <LayoutGrid className="w-4 h-4 text-qv-secondary" />}
              </button>
              <button
                onClick={() => navigate("/locales")}
                aria-label={t("feed.locales")}
                className="flex items-center justify-center w-9 h-9 text-white bg-white/[0.08] border border-white/10 rounded-full active:scale-95"
                data-testid="feed-locales-btn"
              >
                <Building2 className="w-4 h-4 text-qv-secondary" />
              </button>
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
          >
          <p className="flex items-center gap-2 mt-3 lg:mt-5 text-[11px] font-bold uppercase tracking-[0.22em] text-white/50">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-qv-primary/70" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-qv-primary" />
            </span>
            {WEEKDAYS_ES[now.getDay()]} {pad2(now.getHours())}:{pad2(now.getMinutes())}
          </p>
          <h1 className="font-display text-[34px] sm:text-[42px] lg:text-6xl font-black tracking-[-0.035em] mt-1.5 lg:mt-2 leading-[0.95] lg:leading-[0.9]">
            ¿Dónde está<br />la noche<span className="text-qv-primary">?</span>
          </h1>
          </motion.div>
        </div>
      </header>

      {/* Stories over Block A (handles its own empty state) */}
      {user && <StoriesBar />}

      {/* Privacy ghost-mode reminder (rare) */}
      {user && showPrivacyReminder && (
        <div className="px-4 pt-1 pb-1">
          <div data-testid="privacy-reminder" className="w-full rounded-2xl border border-white/12 bg-white/5 p-3 flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center shrink-0">
              <EyeOff className="w-4 h-4 text-white/70" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-semibold leading-tight">{t("feed.hidden_mode_title")}</p>
              <p className="text-white/55 text-xs">{t("feed.hidden_mode_body")}</p>
            </div>
            <button onClick={() => { dismissPrivacyReminder(); navigate("/ajustes"); }} data-testid="privacy-reminder-settings" className="shrink-0 text-xs font-bold text-qv-secondary bg-qv-secondary/15 border border-qv-secondary/40 rounded-full px-3 py-1.5 active:scale-95">
              {t("feed.settings")}
            </button>
            <button onClick={dismissPrivacyReminder} data-testid="privacy-reminder-dismiss" aria-label={t("feed.dismiss")} className="shrink-0 text-white/40 active:scale-90">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Guest / invite conversion banner */}
      {!user && inviteFrom && (
        <div className="px-4 pt-1 pb-1">
          <div data-testid="feed-invite-banner" className="w-full rounded-2xl border border-qv-secondary/50 bg-gradient-to-r from-qv-secondary/15 to-qv-primary/15 p-3 flex items-center gap-3 text-left">
            <div className="w-10 h-10 rounded-full bg-qv-secondary/20 flex items-center justify-center shrink-0">
              <UserPlus className="w-5 h-5 text-qv-secondary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display font-black text-white text-sm leading-tight">
                <span className="text-qv-secondary">@{inviteFrom}</span> {t("feed.invited_suffix")}
              </p>
              <p className="text-white/60 text-xs">{t("feed.invited_sub")}</p>
            </div>
            <button onClick={() => requireAuth(`aceptar la invitaci\u00f3n de @${inviteFrom}`)} data-testid="feed-invite-accept" className="shrink-0 text-xs font-bold text-black bg-qv-secondary rounded-full px-4 py-2 active:scale-95">
              {t("feed.accept")}
            </button>
          </div>
        </div>
      )}

      {!user && !inviteFrom && (
        <div className="px-4 pt-1 pb-1">
          <div data-testid="feed-guest-banner" className="w-full rounded-2xl border border-qv-primary/35 bg-gradient-to-r from-qv-primary/12 to-qv-secondary/10 px-3 py-2.5 flex items-center gap-2.5 text-left">
            <div className="w-8 h-8 rounded-full bg-qv-primary/20 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 text-qv-primary" />
            </div>
            <p className="flex-1 min-w-0 text-white text-[13px] font-semibold leading-tight">{t("feed.guest_title")}</p>
            <button onClick={() => requireAuth("empezar")} data-testid="feed-guest-register" className="shrink-0 text-xs font-bold text-white bg-qv-primary rounded-full px-4 py-2 active:scale-95">
              {t("feed.enter")}
            </button>
          </div>
        </div>
      )}

      {/* Search — always visible but light (discoverable without crowding) */}
      <div className="px-4 pt-2 pb-1">
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/45 pointer-events-none" />
          <input
            data-testid="feed-search-input"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("feed.search_placeholder", "Busca fiesta, discoteca o estilo\u2026")}
            className="w-full h-10 rounded-full bg-white/[0.045] border border-white/10 pl-10 pr-10 text-sm text-white placeholder-white/45 focus:outline-none focus:border-qv-primary/50 focus:bg-white/[0.07] transition-all"
          />
          {isSearching && (
            <button data-testid="feed-search-clear" onClick={() => setQ("")} aria-label={t("common.clear", "Borrar")} className="absolute right-2.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* ---- SEARCH MODE: flat filtered list ---- */}
      {isSearching ? (
        <div className="px-4 pt-3 pb-6">
          {isLoading ? (
            <SkeletonList />
          ) : filteredEvents.length > 0 ? (
            renderList(filteredEvents)
          ) : (
            <div className="text-center py-16 px-6" data-testid="feed-search-empty">
              <Search className="w-12 h-12 text-white/30 mx-auto mb-4" />
              <p className="text-white/60">{t("feed.search_empty_title", "Sin resultados para \u201c{{q}}\u201d", { q })}</p>
              <p className="text-white/40 text-sm mt-1">{t("feed.search_empty_body", "Prueba con otro nombre de fiesta, discoteca o estilo.")}</p>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-8 px-4 pt-4 pb-10">
          {isLoading ? (
            <SkeletonList />
          ) : (
            <>
              {/* Tus planes abiertos (oculto si no hay) */}
              <MyOpenPlans />

              {/* Banner permanente: montar un plan compartible para esta noche */}
              <MontaPlanBanner city={effectiveCity} />

              {/* Se está moviendo (oculto si no hay actividad real) */}
              <MovingNow events={events} todayStr={todayStr} />

              {/* ===== BLOQUE A · 🔥 ESTA NOCHE ===== */}
              <section data-testid="tonight-block-today">
                <SectionHeader icon={Flame} title="Esta noche" count={blockToday.length} tint="primary" />
                {nothingTonight ? (
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-6 text-center">
                    <PartyPopper className="w-9 h-9 text-white/30 mx-auto mb-2" />
                    <p className="text-white/60 text-sm">Hoy aún no hay fiestas confirmadas en {cityLabel.split(",")[0]}.</p>
                    <p className="text-white/40 text-xs mt-1">Mira lo que viene más abajo 👇</p>
                  </div>
                ) : (
                  renderList(blockToday)
                )}
              </section>

              {/* ===== BLOQUE B · ⚡ TU GENTE ===== (oculto si no hay) */}
              {user && blockFriends.length > 0 && (
                <section data-testid="tonight-block-friends">
                  <SectionHeader icon={Users} title="Tu gente" tint="secondary" />
                  {renderList(blockFriends)}
                </section>
              )}

              {/* Nuevo por aquí (sin amigos) — empuje suave a Descubrir, sin redirigir */}
              {noFriends && (
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
                    <p className="text-white/60 text-xs">Encuentra gente para no salir solo.</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-white/40 shrink-0" />
                </button>
              )}

              {/* ===== BLOQUE C · 🌙 PRÓXIMAMENTE ===== */}
              {blockUpcoming.length > 0 && (
                <section data-testid="tonight-block-upcoming">
                  <SectionHeader icon={Moon} title="Próximamente" count={blockUpcoming.length} tint="muted" />
                  {renderList(upcomingShown)}
                  {hasMoreUpcoming && (
                    <div ref={sentinelRef} className="flex justify-center py-6" data-testid="feed-load-more">
                      <div className="w-6 h-6 rounded-full border-2 border-qv-primary/40 border-t-qv-primary animate-spin" />
                    </div>
                  )}
                </section>
              )}

              {/* Feed totalmente vacío */}
              {blockToday.length === 0 && blockFriends.length === 0 && blockUpcoming.length === 0 && (
                <div className="text-center py-16 px-6" data-testid="feed-empty">
                  <PartyPopper className="w-12 h-12 text-white/30 mx-auto mb-4" />
                  <p className="text-white/60">{t("feed.empty_title")}</p>
                  <p className="text-white/40 text-sm mt-1">{t("feed.empty_body")}</p>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </AppShell>
  );
}
