import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ArrowLeft, UserPlus, Check, Loader2, Compass, Zap, Users, ImageOff, X } from "lucide-react";
import { toast } from "sonner";

function timeAgo(iso) {
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 3600) return `hace ${Math.max(1, Math.floor(diff / 60))} min`;
    if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
    return `hace ${Math.floor(diff / 86400)} d`;
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
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [lightbox, setLightbox] = useState(null);
  const [sentIds, setSentIds] = useState(() => new Set());

  const { data, isLoading } = useQuery({
    queryKey: ["discover"],
    queryFn: async () => (await api.get("/discover")).data,
    staleTime: 60_000,
  });

  const people = data?.people || [];
  const moments = data?.moments || [];
  const city = data?.city || "";

  const sendReq = useMutation({
    mutationFn: async (userId) => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: (d, userId) => {
      setSentIds((prev) => new Set(prev).add(userId));
      toast.success(d.status === "accepted" ? "¡Ya sois amigos!" : "Solicitud enviada");
      qc.invalidateQueries({ queryKey: ["friends"] });
    },
    onError: (e) => toast.error(e.response?.data?.detail || "No se pudo enviar"),
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
          <h1 className="font-display text-3xl font-black tracking-tighter">Descubrir<span className="text-qv-primary">.</span></h1>
        </div>
      </header>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
      ) : (
        <div className="pb-6">
          {/* People */}
          <section className="px-5" data-testid="discover-people">
            <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Gente para conocer
            </p>
            {people.length === 0 ? (
              <p className="text-white/40 text-sm py-3">
                No hay recomendaciones ahora mismo. Vuelve cuando haya más gente por aquí.
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
                          {p.mutual_friends > 0 && <span className="text-qv-secondary"> · {p.mutual_friends} en común</span>}
                          {p.mutual_friends === 0 && p.going_count > 0 && <span className="text-white/50"> · {p.going_count} planes</span>}
                        </p>
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
              <Zap className="w-3.5 h-3.5 text-qv-primary" /> El Momento por la ciudad
            </p>
            {moments.length === 0 ? (
              <p className="text-white/40 text-sm py-3">
                Todavía nadie comparte su Momento en público. Puedes activarlo tú en Ajustes.
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
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
