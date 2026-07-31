import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Camera, Plus, Play, Trash2, Images, Loader2, X, Share2 } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { toast } from "sonner";

/**
 * Shared album for an event — photos + videos uploaded by anyone with interest.
 * Like an Apple shared album per party.
 */
export function EventAlbum({ eventId, hasInterest }) {
  const qc = useQueryClient();
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [progress, setProgress] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["album", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/album`)).data,
    retry: false,
  });

  const uploadMut = useMutation({
    mutationFn: async (file) => {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post(`/events/${eventId}/album/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      return res.data;
    },
    onSuccess: () => {
      toast.success("¡Subido al álbum! +5 pts");
      qc.invalidateQueries({ queryKey: ["album", eventId] });
      qc.invalidateQueries({ queryKey: ["badges", "me"] });
      setUploading(false);
      setProgress(0);
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "No se pudo subir");
      setUploading(false);
      setProgress(0);
    },
  });

  const deleteMut = useMutation({
    mutationFn: async (uploadId) => (await api.delete(`/events/${eventId}/album/${uploadId}`)).data,
    onSuccess: () => {
      toast.success("Eliminado");
      qc.invalidateQueries({ queryKey: ["album", eventId] });
      setPreview(null);
    },
  });

  const onPick = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) {
      toast.error("Máx 50MB");
      return;
    }
    setUploading(true);
    uploadMut.mutate(file);
    e.target.value = "";
  };

  if (isLoading) return null;
  if (!data) {
    return (
      <div className="text-white/40 text-xs italic">Marca ‘Voy’ o ‘Estuve’ para acceder al álbum.</div>
    );
  }

  const items = data.items || [];
  const eventName = data.event?.name || "";

  const shareAlbum = async () => {
    const url = `${window.location.origin}/event/${eventId}`;
    const text = `Mira el álbum compartido de ${eventName} 📸 ${items.length} recuerdo${items.length === 1 ? "" : "s"} · ${url}`;
    try {
      if (navigator.share) await navigator.share({ title: eventName, text, url });
      else {
        window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
      }
    } catch {
      /* cancelled */
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="flex items-center gap-2 text-xs uppercase tracking-widest text-white/40 font-bold">
          <Images className="w-4 h-4 text-qv-secondary" /> Álbum compartido <span className="text-white/30">({items.length})</span>
        </p>
        {items.length > 0 && (
          <button
            data-testid="album-share-btn"
            onClick={shareAlbum}
            className="flex items-center gap-1 text-qv-secondary text-xs font-bold active:opacity-70"
          >
            <Share2 className="w-3.5 h-3.5" /> Compartir
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-6 text-center">
          <Images className="w-8 h-8 text-white/30 mx-auto mb-2" />
          <p className="text-white/50 text-sm mb-3">Aún no hay recuerdos de esta fiesta.</p>
          {hasInterest && (
            <button
              data-testid="album-empty-upload"
              onClick={() => inputRef.current?.click()}
              className="h-10 px-4 rounded-full bg-qv-primary text-white font-bold text-sm active:scale-95"
            >
              <Plus className="w-4 h-4 inline mr-1" /> Sube la primera
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-1.5" data-testid="album-grid">
          {hasInterest && (
            <button
              data-testid="album-add-btn"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="aspect-square rounded-xl border border-dashed border-white/25 bg-white/[0.03] flex flex-col items-center justify-center text-white/60 active:scale-95 disabled:opacity-50"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span className="text-[10px] mt-1">{progress}%</span>
                </>
              ) : (
                <>
                  <Plus className="w-6 h-6" />
                  <span className="text-[10px] mt-1">Subir</span>
                </>
              )}
            </button>
          )}
          {items.map((it) => (
            <button
              key={it.id}
              onClick={() => setPreview(it)}
              data-testid={`album-item-${it.id}`}
              className="aspect-square rounded-xl overflow-hidden bg-black relative active:scale-95"
            >
              {it.media_type === "video" ? (
                <>
                  <video src={mediaUrl(it.media_url)} className="w-full h-full object-cover" muted playsInline preload="metadata" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Play className="w-8 h-8 text-white drop-shadow-lg" fill="white" />
                  </div>
                </>
              ) : (
                <img src={mediaUrl(it.media_url)} alt="" className="w-full h-full object-cover" loading="lazy" />
              )}
              <div className="absolute bottom-1 left-1 flex items-center gap-1">
                <AvatarCircle name={it.author?.name || ""} picture={it.author?.picture || ""} size={18} ring={false} />
              </div>
            </button>
          ))}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*,video/*"
        onChange={onPick}
        className="hidden"
        data-testid="album-file-input"
      />

      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="bg-black border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden">
          {preview && (
            <div className="relative">
              <button
                onClick={() => setPreview(null)}
                className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center"
              >
                <X className="w-5 h-5 text-white" />
              </button>
              {preview.media_type === "video" ? (
                <video src={mediaUrl(preview.media_url)} controls autoPlay className="w-full max-h-[70vh]" />
              ) : (
                <img src={mediaUrl(preview.media_url)} alt="" className="w-full max-h-[70vh] object-contain" />
              )}
              <div className="p-4 flex items-center gap-3">
                <AvatarCircle name={preview.author?.name || ""} picture={preview.author?.picture || ""} size={32} ring={false} />
                <div className="flex-1">
                  <p className="text-white text-sm font-semibold">{preview.author?.name}</p>
                  <p className="text-white/40 text-xs">{new Date(preview.created_at).toLocaleString("es-ES")}</p>
                </div>
                {preview.is_mine && (
                  <button
                    data-testid="album-delete-btn"
                    onClick={() => deleteMut.mutate(preview.id)}
                    disabled={deleteMut.isPending}
                    className="w-9 h-9 rounded-full bg-red-500/20 flex items-center justify-center active:scale-95"
                  >
                    <Trash2 className="w-4 h-4 text-red-300" />
                  </button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
