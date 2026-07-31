import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Plus, X, Loader2, ImageUp, Trash2, CameraIcon } from "lucide-react";
import { toast } from "sonner";

function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "ahora";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  return `hace ${Math.floor(diff / 3600)} h`;
}

function groupByUser(stories) {
  const map = new Map();
  for (const s of stories) {
    if (!map.has(s.user_id)) map.set(s.user_id, { user_id: s.user_id, author: s.author, is_mine: s.is_mine, stories: [] });
    map.get(s.user_id).stories.push(s);
  }
  const groups = [...map.values()];
  groups.sort((a, b) => (a.is_mine ? -1 : 0) - (b.is_mine ? -1 : 0));
  return groups;
}

export function AddStoryDialog({ open, onOpenChange, eventId }) {
  const qc = useQueryClient();
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setPreview("");
    setCaption("");
  };

  const pick = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("caption", caption);
      if (eventId) fd.append("event_id", eventId);
      await api.post("/stories", fd, { headers: { "Content-Type": "multipart/form-data" } });
      qc.invalidateQueries({ queryKey: ["stories"] });
      toast.success("¡Historia publicada! Desaparecerá en 24h");
      reset();
      onOpenChange(false);
    } catch {
      toast.error("No se pudo publicar la historia");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl">
        <DialogHeader>
          <DialogTitle className="font-display">Subir historia</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div
            onClick={() => fileRef.current?.click()}
            className="relative aspect-[4/5] rounded-2xl overflow-hidden border border-white/15 bg-white/5 flex items-center justify-center cursor-pointer"
            data-testid="story-drop"
          >
            {preview ? (
              <img src={preview} alt="preview" className="w-full h-full object-cover" />
            ) : (
              <div className="text-white/40 flex flex-col items-center gap-2 text-sm">
                <ImageUp className="w-7 h-7" /> Elige una foto de anoche
              </div>
            )}
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={pick} data-testid="story-file-input" />
          </div>
          <Input
            data-testid="story-caption"
            placeholder="Añade un texto (opcional)"
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            className="h-11 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40"
          />
          <button
            data-testid="story-submit"
            onClick={submit}
            disabled={!file || busy}
            className="h-12 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : "Compartir con mis amigos"}
          </button>
          <p className="text-white/40 text-xs text-center">Solo la verán tus amigos · desaparece en 24h</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AddStoryButton({ eventId, className = "", label = "Subir historia" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button data-testid="add-story-detail-btn" onClick={() => setOpen(true)} className={className}>
        <CameraIcon className="w-4 h-4" /> {label}
      </button>
      <AddStoryDialog open={open} onOpenChange={setOpen} eventId={eventId} />
    </>
  );
}

function StoryViewer({ group, onClose }) {
  const qc = useQueryClient();
  const [idx, setIdx] = useState(0);
  const story = group.stories[idx];

  const del = useMutation({
    mutationFn: async () => (await api.delete(`/stories/${story.id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
      toast.success("Historia eliminada");
      onClose();
    },
  });

  const nav = (e) => {
    const x = e.clientX;
    const w = window.innerWidth;
    if (x < w * 0.33) setIdx((i) => Math.max(0, i - 1));
    else {
      if (idx >= group.stories.length - 1) onClose();
      else setIdx((i) => i + 1);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black flex flex-col" data-testid="story-viewer">
      {/* progress segments */}
      <div className="absolute top-2 left-3 right-3 flex gap-1 z-20">
        {group.stories.map((_, i) => (
          <div key={i} className="flex-1 h-1 rounded-full bg-white/25 overflow-hidden">
            <div className={`h-full bg-white transition-all ${i <= idx ? "w-full" : "w-0"}`} />
          </div>
        ))}
      </div>

      <div className="absolute top-5 left-3 right-3 flex items-center gap-3 z-20">
        <AvatarCircle name={group.author.name} picture={group.author.picture} size={36} ring={false} />
        <div className="flex-1 min-w-0">
          <p className="text-white font-semibold text-sm truncate">{group.is_mine ? "Tu historia" : group.author.name}</p>
          <p className="text-white/60 text-xs">{timeAgo(story.created_at)}</p>
        </div>
        {group.is_mine && (
          <button data-testid="story-delete" onClick={() => del.mutate()} className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center">
            <Trash2 className="w-4 h-4 text-white/80" />
          </button>
        )}
        <button data-testid="story-close" onClick={onClose} className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center">
          <X className="w-5 h-5 text-white" />
        </button>
      </div>

      <div className="flex-1 flex items-center justify-center" onClick={nav} data-testid="story-nav-area">
        <img src={mediaUrl(story.image_url)} alt="" className="max-w-full max-h-full object-contain" />
      </div>

      <div className="absolute bottom-8 left-4 right-4 z-20 pointer-events-none">
        {story.event_name && (
          <span className="inline-block qv-glass text-white text-xs font-semibold px-3 py-1 rounded-full border border-white/15 mb-2">
            🎉 {story.event_name}
          </span>
        )}
        {story.caption && <p className="text-white text-base leading-snug" style={{ textShadow: "0 1px 8px rgba(0,0,0,0.8)" }}>{story.caption}</p>}
      </div>
    </div>
  );
}

export function StoriesBar() {
  const [addOpen, setAddOpen] = useState(false);
  const [viewer, setViewer] = useState(null);

  const { data: stories = [] } = useQuery({
    queryKey: ["stories"],
    queryFn: async () => (await api.get("/stories")).data,
    refetchInterval: 60000,
  });

  const groups = groupByUser(stories);

  return (
    <>
      <div className="flex overflow-x-auto hide-scrollbar gap-4 px-5 py-3" data-testid="stories-bar">
        <button
          data-testid="add-story-btn"
          onClick={() => setAddOpen(true)}
          className="flex flex-col items-center gap-1.5 shrink-0"
        >
          <div className="w-16 h-16 rounded-full border-2 border-dashed border-white/25 flex items-center justify-center bg-white/5">
            <Plus className="w-6 h-6 text-white/70" />
          </div>
          <span className="text-[11px] text-white/60 font-medium">Tu historia</span>
        </button>

        {groups.map((g) => (
          <button
            key={g.user_id}
            data-testid={`story-bubble-${g.author.username}`}
            onClick={() => setViewer(g)}
            className="flex flex-col items-center gap-1.5 shrink-0"
          >
            <div className="w-16 h-16 rounded-full p-[2.5px] bg-gradient-to-tr from-qv-primary to-qv-secondary">
              <div className="w-full h-full rounded-full p-[2px] bg-[#0A0A0C]">
                <AvatarCircle name={g.author.name} picture={g.author.picture} size={54} ring={false} className="w-full h-full" />
              </div>
            </div>
            <span className="text-[11px] text-white/70 font-medium truncate max-w-[64px]">
              {g.is_mine ? "Tú" : g.author.name.split(" ")[0]}
            </span>
          </button>
        ))}
      </div>

      <AddStoryDialog open={addOpen} onOpenChange={setAddOpen} />
      {viewer && <StoryViewer group={viewer} onClose={() => setViewer(null)} />}
    </>
  );
}
