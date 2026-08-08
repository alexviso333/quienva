import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ArrowLeft, UserPlus, Check, Loader2, Compass, Zap, Users, ImageOff, X, Heart } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

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
      <div className={`flex items-center justify-center bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f] text-white/30 ${className}`}>
        <ImageOff className="w-6 h-6" />
      </div>
    );
  }
  return <img src={src} alt="" className={className} loading="lazy" onError={() => setBroken(true)} />;
}

export default function Descubrir() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [lightbox, setLightbox] = useState(null);
  const [sentIds, setSentIds] = useState(() => new Set());
  const [onlyMatches, setOnlyMatches] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["discover"],
    queryFn: async () => (await api.get("/discover")).data,
    staleTime: 60_000,
  });

  const allPeople = data?.people || [];
  const people = onlyMatches ? allPeople.filter((p) => p.shared_events > 0) : allPeople;
  const matchesCount = allPeople.filter((p) => p.shared_events > 0).length;
  const moments = data?.moments || [];
  const city = data?.city || "";

  const sendReq = useMutation({
    mutationFn: async (userId) => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: (d, userId) => {
      setSentIds((prev) => new Set(prev).add(userId));
      toast.success(d.status === "accepted" ? "¡Ya sois amigos!" : "Solicitud enviada");
      qc.invalidateQueries({ queryKey: ["friends"] });
    },
    onError: (e) => toast.error(e.response?.data?.detail || t("discover.toast_error")),
  });

  const likeMoment = useMutation({
    mutationFn: async (m) => (await api.post(`/captures/${m.id}/like`)).data,
    onMutate: async (m) => {
      await qc.cancelQueries({ queryKey: ["discover"] });
      const prev = qc.getQueryData(["discover"]);
      const flip = (x) => ({ ...x, i_liked: !x.i_liked, likes: Math.max(0, (x.likes || 0) + (x.i_liked ? -1 : 1)) });
      qc.setQueryData(["discover"], (d) =>
        d ? { ...d, moments: d.moments.map((x) => (x.id === m.id ? flip(x) : x)) } : d);
      setLightbox((lb) => (lb && lb.id === m.id ? flip(lb) : lb));
      return { prev };
    },
    onError: (_e, _m, ctx) => { if (ctx?.prev) qc.setQueryData(["discover"], ctx.prev); },
  });

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} data-testid="descubrir-back" className="w-10 h-10 rounded-full qv-glass border border-white/15 flex items-center justify-center active:scale-90">
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>
        <div>
          <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold flex items-center gap-1.5">
            <Compass className="w-3.5 h-3.5" /> {city}
          </p>
          <h1 className="font-display text-3xl font-black tracking-tighter">{t("discover.title")}<span className="text-qv-primary">.</span></h1>
        </div>
      </header>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
      ) : (
        <div className="pb-6">
          {/* People */}
          <section className="px-5" data-testid="discover-people">
            <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> {t("discover.people")}
            </p>
            {matchesCount > 0 && (
              <div className="flex gap-1.5 mb-3" data-testid="discover-people-filter">
                <button
                  onClick={() => setOnlyMatches(false)}
                  className={`rounded-full px-3 py-1.5 text-xs font-bold ${!onlyMatches ? "bg-qv-primary text-white" : "bg-white/5 border border-white/10 text-white/60"}`}
                >
                  {t("discover.all")}
                </button>
                <button
                  data-testid="filter-matches"
                  onClick={() => setOnlyMatches(true)}
                  className={`rounded-full px-3 py-1.5 text-xs font-bold flex items-center gap-1 ${onlyMatches ? "bg-qv-secondary text-black" : "bg-white/5 border border-white/10 text-white/60"}`}
                >
                  <Zap className="w-3 h-3" /> {t("discover.matches", { count: matchesCount })}
                </button>
              </div>
            )}
            {people.length === 0 ? (
              <p className="text-white/40 text-sm py-3">
                {onlyMatches ? "Nadie coincide con tus planes de esta semana todavía." : "No hay recomendaciones ahora mismo. Vuelve cuando haya más gente por aquí."}
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {people.map((p) => {
                  const sent = sentIds.has(p.user_id);
                  return (
                    <div key={p.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`discover-person-${p.user_id}`}>
                      <button onClick={() => navigate(`/users/${p.user_id}`)} className="active:scale-95">
                        <AvatarCircle name={p.name} picture={p.picture} size={44} ring={false} />
                      </button>
                      <button onClick={() => navigate(`/users/${p.user_id}`)} className="flex-1 min-w-0 text-left">
                        <p className="font-semibold truncate">{p.name}</p>
                        <p className="text-white/40 text-sm truncate">
                          @{p.username}
                          {p.mutual_friends > 0 && <span className="text-qv-secondary"> {t("discover.mutual", { count: p.mutual_friends })}</span>}
                          {p.mutual_friends === 0 && p.going_count > 0 && <span className="text-white/50"> {t("discover.plans", { count: p.going_count })}</span>}
                        </p>
                        {p.shared_events > 0 && (
                          <span className="inline-flex items-center gap-1 mt-1 text-[10px] font-black uppercase tracking-wide text-black bg-qv-secondary rounded-full px-2 py-0.5">
                            <Zap className="w-2.5 h-2.5" /> {t("discover.shared", { count: p.shared_events })}
                          </span>
                        )}
                      </button>
                      <button
                        data-testid={`discover-add-${p.user_id}`}
                        disabled={sent || sendReq.isPending}
                        onClick={() => sendReq.mutate(p.user_id)}
                        className={`h-9 px-4 rounded-full text-sm font-semibold flex items-center gap-1.5 active:scale-95 disabled:opacity-70 ${sent ? "bg-white/10 text-white/60" : "bg-qv-primary text-white"}`}
                      >
                        {sent ? <><Check className="w-4 h-4" /> Enviada</> : <><UserPlus className="w-4 h-4" /> Añadir</>}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Public moments */}
          <section className="px-5 mt-7" data-testid="discover-moments">
            <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-qv-primary" /> {t("discover.moment_city")}
            </p>
            {moments.length === 0 ? (
              <p className="text-white/40 text-sm py-3">
                {t("discover.empty_moments")}
              </p>
            ) : (
              <div className="grid grid-cols-3 gap-2" data-testid="discover-moments-grid">
                {moments.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setLightbox(m)}
                    data-testid={`discover-moment-${m.id}`}
                    className="relative aspect-[3/4] rounded-xl overflow-hidden border border-white/10 bg-white/5 active:scale-95"
                  >
                    <MomentImg src={mediaThumb(m.image_url, 400)} className="w-full h-full object-cover" />
                    {m.likes > 0 && (
                      <span className="absolute top-1.5 right-1.5 flex items-center gap-0.5 text-[10px] font-bold text-white bg-black/55 rounded-full px-1.5 py-0.5">
                        <Heart className="w-2.5 h-2.5" fill={m.i_liked ? "#ff0055" : "none"} stroke={m.i_liked ? "#ff0055" : "currentColor"} /> {m.likes}
                      </span>
                    )}
                    <div className="absolute inset-x-0 bottom-0 p-1.5 bg-gradient-to-t from-black/80 to-transparent flex items-center gap-1">
                      <AvatarCircle name={m.author?.name} picture={m.author?.picture} size={16} ring={false} />
                      <span className="text-[10px] text-white/90 font-semibold truncate">{m.author?.name?.split(" ")[0]}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      <Dialog open={!!lightbox} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="bg-black border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden">
          {lightbox && (
            <div className="relative">
              <button onClick={() => setLightbox(null)} className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center">
                <X className="w-5 h-5 text-white" />
              </button>
              <MomentImg src={mediaThumb(lightbox.image_url, 1000)} className="w-full max-h-[75vh] object-contain" />
              <div className="p-3 flex items-center gap-2">
                <button onClick={() => { navigate(`/users/${lightbox.author_id}`); setLightbox(null); }} className="flex items-center gap-2 flex-1 min-w-0 text-left active:scale-95">
                  <AvatarCircle name={lightbox.author?.name} picture={lightbox.author?.picture} size={34} ring={false} />
                  <div className="min-w-0">
                    <p className="font-semibold truncate text-sm">{lightbox.author?.name}</p>
                    <p className="text-white/40 text-xs truncate">
                      {lightbox.event_name ? `🎉 ${lightbox.event_name} · ` : ""}{timeAgo(lightbox.created_at)}
                    </p>
                  </div>
                </button>
                <button
                  data-testid={`moment-like-${lightbox.id}`}
                  onClick={() => likeMoment.mutate(lightbox)}
                  className={`shrink-0 flex items-center gap-1.5 h-10 px-4 rounded-full font-bold active:scale-95 ${lightbox.i_liked ? "bg-qv-primary/20 text-qv-primary" : "bg-white/10 text-white"}`}
                >
                  <Heart className="w-4 h-4" fill={lightbox.i_liked ? "currentColor" : "none"} /> {lightbox.likes || 0}
                </button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
