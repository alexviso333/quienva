import { useEffect, useRef, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { ArrowLeft, Loader2, Heart, ImageOff, Compass, Users, Camera, Zap } from "lucide-react";
import i18n from "@/i18n";

const PAGE = 8;

function timeAgo(iso) {
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 3600) return i18n.t("notifs.ago_min", { n: Math.max(1, Math.floor(diff / 60)) });
    if (diff < 86400) return i18n.t("notifs.ago_hour", { n: Math.floor(diff / 3600) });
    return i18n.t("notifs.ago_day", { n: Math.floor(diff / 86400) });
  } catch {
    return "";
  }
}

function MomentImg({ src, className = "" }) {
  const [broken, setBroken] = useState(false);
  if (!src || broken) {
    return (
      <div className={`flex items-center justify-center bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f] text-white/25 ${className}`}>
        <ImageOff className="w-8 h-8" />
      </div>
    );
  }
  return <img src={src} alt="" className={className} loading="lazy" onError={() => setBroken(true)} />;
}

function MomentCard({ m, onLike, onOpenAuthor, onOpenEvent }) {
  return (
    <div className="relative rounded-3xl overflow-hidden border border-white/10 bg-white/5" data-testid={`moment-card-${m.id}`}>
      <MomentImg src={mediaThumb(m.image_url, 900)} className="w-full aspect-[4/5] object-cover" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/45 via-transparent to-black/80" />

      <button
        onClick={() => onOpenAuthor(m.author_id)}
        className="absolute top-3 left-3 flex items-center gap-2 active:scale-95"
        data-testid={`moment-author-${m.id}`}
      >
        <AvatarCircle name={m.author?.name} picture={m.author?.picture} size={38} ring />
        <span className="font-semibold text-sm text-white drop-shadow">{m.author?.name}</span>
      </button>

      <div className="absolute inset-x-0 bottom-0 p-4 flex items-end justify-between gap-3">
        <div className="min-w-0">
          {m.event_name && (
            <button
              onClick={() => m.event_id && onOpenEvent(m.event_id)}
              className="max-w-full inline-flex items-center gap-1.5 rounded-full bg-black/45 backdrop-blur px-3 py-1.5 text-xs font-bold text-white active:scale-95"
              data-testid={`moment-event-${m.id}`}
            >
              <Zap className="w-3.5 h-3.5 text-qv-primary shrink-0" />
              <span className="truncate">{m.event_name}</span>
            </button>
          )}
          <p className="text-white/70 text-xs mt-2 drop-shadow">{timeAgo(m.created_at)}</p>
        </div>
        <button
          onClick={() => onLike(m)}
          data-testid={`moment-like-${m.id}`}
          className={`shrink-0 flex flex-col items-center gap-0.5 active:scale-90 transition-transform ${m.i_liked ? "text-qv-primary" : "text-white"}`}
        >
          <span className="w-12 h-12 rounded-full bg-black/45 backdrop-blur flex items-center justify-center">
            <Heart className="w-6 h-6" fill={m.i_liked ? "currentColor" : "none"} />
          </span>
          <span className="text-xs font-bold drop-shadow">{m.likes || 0}</span>
        </button>
      </div>
    </div>
  );
}

export default function Momentos() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [scope, setScope] = useState("amigos");
  const sentinelRef = useRef(null);

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ["moments-feed", scope],
    queryFn: async ({ pageParam = 0 }) =>
      (await api.get(`/moments/feed?scope=${scope}&skip=${pageParam}&limit=${PAGE}`)).data,
    getNextPageParam: (last, pages) => (last.has_more ? pages.length * PAGE : undefined),
    staleTime: 30_000,
  });

  const moments = useMemo(() => (data?.pages || []).flatMap((p) => p.moments || []), [data]);

  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) return;
    const io = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) fetchNextPage(); },
      { rootMargin: "400px" }
    );
    io.observe(sentinelRef.current);
    return () => io.disconnect();
  }, [hasNextPage, fetchNextPage, moments.length]);

  const likeMoment = useMutation({
    mutationFn: async (m) => (await api.post(`/captures/${m.id}/like`)).data,
    onMutate: async (m) => {
      await qc.cancelQueries({ queryKey: ["moments-feed", scope] });
      const prev = qc.getQueryData(["moments-feed", scope]);
      qc.setQueryData(["moments-feed", scope], (d) =>
        d
          ? {
              ...d,
              pages: d.pages.map((pg) => ({
                ...pg,
                moments: pg.moments.map((x) =>
                  x.id === m.id
                    ? { ...x, i_liked: !x.i_liked, likes: Math.max(0, (x.likes || 0) + (x.i_liked ? -1 : 1)) }
                    : x
                ),
              })),
            }
          : d
      );
      return { prev };
    },
    onError: (_e, _m, ctx) => { if (ctx?.prev) qc.setQueryData(["moments-feed", scope], ctx.prev); },
  });

  const Toggle = ({ value, icon: Icon, label }) => {
    const on = scope === value;
    return (
      <button
        onClick={() => setScope(value)}
        data-testid={`momentos-toggle-${value}`}
        className={`flex-1 flex items-center justify-center gap-2 rounded-full py-2.5 text-sm font-bold transition-colors active:scale-[0.98] ${
          on ? "bg-qv-primary text-white shadow-[0_0_16px_rgba(255,0,85,0.4)]" : "text-white/55"
        }`}
      >
        <Icon className="w-4 h-4" /> {label}
      </button>
    );
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3 flex items-center gap-3" data-testid="momentos-header">
        <button
          onClick={() => navigate(-1)}
          data-testid="momentos-back"
          className="w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center active:scale-90"
        >
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <h1 className="font-display text-3xl font-black tracking-tighter">
          Momentos<span className="text-qv-primary">.</span>
        </h1>
      </header>

      <div className="sticky top-0 z-20 px-5 pt-2 pb-3 bg-gradient-to-b from-[#0a0a0c] via-[#0a0a0c]/95 to-transparent">
        <div className="flex gap-1 p-1 rounded-full bg-white/5 border border-white/10" data-testid="momentos-toggle">
          <Toggle value="amigos" icon={Users} label="Amigos" />
          <Toggle value="discover" icon={Compass} label="Descubrir" />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-24"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
      ) : moments.length === 0 ? (
        <div className="px-6 py-20 text-center flex flex-col items-center gap-4" data-testid="momentos-empty">
          <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
            <Camera className="w-7 h-7 text-white/40" />
          </div>
          <p className="text-white/50 text-sm max-w-xs">
            {scope === "amigos"
              ? "Tus amigos aún no han subido ningún Momento. ¡Sé tú quien empiece la noche!"
              : "Todavía no hay Momentos públicos en tu ciudad. Vuelve más tarde o comparte el tuyo."}
          </p>
          <button
            onClick={() => navigate("/momento")}
            data-testid="momentos-capture-cta"
            className="flex items-center gap-2 rounded-full bg-qv-primary text-white font-bold px-5 py-3 active:scale-95"
          >
            <Camera className="w-4 h-4" /> Hacer mi Momento
          </button>
        </div>
      ) : (
        <div className="px-4 pb-8 flex flex-col gap-5" data-testid="momentos-feed">
          {moments.map((m) => (
            <MomentCard
              key={m.id}
              m={m}
              onLike={likeMoment.mutate}
              onOpenAuthor={(id) => navigate(`/users/${id}`)}
              onOpenEvent={(id) => navigate(`/event/${id}`)}
            />
          ))}
          <div ref={sentinelRef} data-testid="momentos-load-more" className="h-8 flex items-center justify-center">
            {isFetchingNextPage && <Loader2 className="w-5 h-5 text-qv-primary animate-spin" />}
          </div>
        </div>
      )}
    </AppShell>
  );
}
