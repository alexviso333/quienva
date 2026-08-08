import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Plus, X, Loader2, ImageUp, Trash2, CameraIcon, Send, ImageOff } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

/**
 * Renders an image but degrades gracefully to a branded placeholder when the
 * source is missing or fails to load (e.g. old stories whose file was lost on
 * an ephemeral disk). Avoids the ugly browser "?" broken-image glyph.
 */
function SafeImg({ src, className = "", alt = "" }) {
  const [broken, setBroken] = useState(false);
  if (!src || broken) {
    return (
      <div className={`flex items-center justify-center bg-gradient-to-br from-[#2a0a1a] via-[#121215] to-[#0a1a1f] text-white/30 ${className}`}>
        <ImageOff className="w-6 h-6" />
      </div>
    );
  }
  return <img src={src} alt={alt} className={className} loading="lazy" onError={() => setBroken(true)} />;
}

function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return i18n.t("stories.timeago_now");
  if (diff < 3600) return i18n.t("stories.timeago_min", { n: Math.floor(diff / 60) });
  return i18n.t("stories.timeago_hour", { n: Math.floor(diff / 3600) });
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
  const { t } = useTranslation();
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
    if (!f.type.startsWith("image/")) {
      toast.error(t("stories.err_image_type"));
      return;
    }
    if (f.size > 8 * 1024 * 1024) {
      toast.error(t("stories.err_image_size"));
      return;
    }
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
      toast.success(t("stories.toast_published"));
      reset();
      onOpenChange(false);
    } catch {
      toast.error(t("stories.err_publish"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl">
        <DialogHeader>
          <DialogTitle className="font-display">{t("stories.add_title")}</DialogTitle>
          <DialogDescription className="text-white/50">
            {t("stories.add_desc")}
          </DialogDescription>
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
                <ImageUp className="w-7 h-7" /> {t("stories.choose_photo")}
              </div>
            )}
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={pick} data-testid="story-file-input" />
          </div>
          <Input
            data-testid="story-caption"
            placeholder={t("stories.caption_ph")}
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
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : t("stories.share_with_friends")}
          </button>
          <p className="text-white/40 text-xs text-center">{t("stories.footer_note")}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AddStoryButton({ eventId, className = "", label }) {
  const [open, setOpen] = useState(false);
  const { t } = useTranslation();
  return (
    <>
      <button data-testid="add-story-detail-btn" onClick={() => setOpen(true)} className={className}>
        <CameraIcon className="w-4 h-4" /> {label || t("stories.upload_button")}
      </button>
      <AddStoryDialog open={open} onOpenChange={setOpen} eventId={eventId} />
    </>
  );
}

function StoryViewer({ group, onClose, startIndex = 0 }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const [idx, setIdx] = useState(startIndex);
  const [reactText, setReactText] = useState("");
  const story = group.stories[idx];

  const del = useMutation({
    mutationFn: async () => (await api.delete(`/stories/${story.id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
      qc.invalidateQueries({ queryKey: ["stories-archive"] });
      toast.success(t("stories.toast_deleted"));
      onClose();
    },
  });

  const react = useMutation({
    mutationFn: async (content) => (await api.post(`/stories/${story.id}/react`, { content })).data,
    onSuccess: () => {
      setReactText("");
      toast.success(t("stories.toast_sent"));
    },
    onError: () => toast.error(t("stories.err_send")),
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
          <p className="text-white font-semibold text-sm truncate">{group.is_mine ? t("stories.your_story") : group.author.name}</p>
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
        <SafeImg src={mediaThumb(story.image_url, 1080)} className="max-w-full max-h-full object-contain" />
      </div>

      <div className="absolute bottom-0 left-0 right-0 z-20 p-4 pb-6 bg-gradient-to-t from-black/80 to-transparent">
        {story.event_name && (
          <span className="inline-block qv-glass text-white text-xs font-semibold px-3 py-1 rounded-full border border-white/15 mb-2">
            🎉 {story.event_name}
          </span>
        )}
        {story.caption && (
          <p className="text-white text-base leading-snug mb-3" style={{ textShadow: "0 1px 8px rgba(0,0,0,0.8)" }}>
            {story.caption}
          </p>
        )}

        {group.is_mine ? (
          (story.reactions && story.reactions.length > 0) ? (
            <div className="flex flex-wrap gap-2" data-testid="story-received-reactions">
              {story.reactions.map((r, i) => (
                <span key={i} className="qv-glass border border-white/15 text-white text-xs px-2.5 py-1 rounded-full">
                  {r.content} · {r.user.name.split(" ")[0]}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-white/50 text-xs">{t("stories.no_reactions")}</p>
          )
        ) : (
          <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
            {["❤️", "🔥", "😂", "😮"].map((emo) => (
              <button
                key={emo}
                data-testid={`story-react-${emo}`}
                onClick={() => react.mutate(emo)}
                className="text-xl active:scale-125 transition-transform shrink-0"
              >
                {emo}
              </button>
            ))}
            <input
              data-testid="story-react-input"
              value={reactText}
              onChange={(e) => setReactText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && reactText.trim()) react.mutate(reactText.trim()); }}
              placeholder={t("stories.react_ph")}
              className="flex-1 min-w-0 h-10 rounded-full bg-white/10 border border-white/20 px-3 text-white text-sm placeholder:text-white/50 outline-none"
            />
            <button
              data-testid="story-react-send"
              onClick={() => reactText.trim() && react.mutate(reactText.trim())}
              className="w-10 h-10 rounded-full bg-qv-primary flex items-center justify-center shrink-0"
            >
              <Send className="w-4 h-4 text-white" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function StoriesBar() {
  const [addOpen, setAddOpen] = useState(false);
  const [viewer, setViewer] = useState(null);
  const { t } = useTranslation();

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
          <span className="text-[11px] text-white/60 font-medium">{t("stories.your_story")}</span>
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
              {g.is_mine ? t("stories.you") : g.author.name.split(" ")[0]}
            </span>
          </button>
        ))}
      </div>

      <AddStoryDialog open={addOpen} onOpenChange={setAddOpen} />
      {viewer && <StoryViewer group={viewer} onClose={() => setViewer(null)} />}
    </>
  );
}

export function StoriesArchive({ open, onOpenChange }) {
  const [viewerIdx, setViewerIdx] = useState(null);
  const { t } = useTranslation();
  const { data: stories = [] } = useQuery({
    queryKey: ["stories-archive"],
    queryFn: async () => (await api.get("/stories/archive")).data,
    enabled: open,
  });

  const myGroup = stories.length
    ? { user_id: stories[0].user_id, is_mine: true, author: stories[0].author, stories }
    : null;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="bg-[#121215] border-white/10 text-white max-w-md rounded-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">{t("stories.archive_title")}</DialogTitle>
            <DialogDescription className="text-white/50">
              {t("stories.archive_desc")}
            </DialogDescription>
          </DialogHeader>
          {stories.length === 0 ? (
            <p className="text-white/40 text-sm py-10 text-center" data-testid="archive-empty">
              {t("stories.archive_empty")}
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-2" data-testid="stories-archive-grid">
              {stories.map((s, i) => (
                <button
                  key={s.id}
                  data-testid={`archive-item-${s.id}`}
                  onClick={() => { setViewerIdx(i); onOpenChange(false); }}
                  className="relative aspect-[3/4] rounded-xl overflow-hidden border border-white/10 bg-white/5"
                >
                  <SafeImg src={mediaThumb(s.image_url, 400)} className="w-full h-full object-cover" />
                  {s.reactions && s.reactions.length > 0 && (
                    <span className="absolute bottom-1 right-1 text-xs bg-black/60 rounded-full px-1.5 py-0.5">
                      {s.reactions.length} 💌
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
      {viewerIdx !== null && myGroup && (
        <StoryViewer
          group={myGroup}
          startIndex={viewerIdx}
          onClose={() => { setViewerIdx(null); onOpenChange(true); }}
        />
      )}
    </>
  );
}
