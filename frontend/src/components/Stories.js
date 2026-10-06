import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import api, { mediaThumb } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Plus, X, Loader2, Trash2, CameraIcon, Send, ImageOff, Heart, Zap, Star, Camera, Images, ChevronLeft } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

const STORY_MS = 5000;
const SEEN_KEY = "qv_stories_seen";

function getSeen() {
  try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]")); } catch { return new Set(); }
}
function markSeen(ids) {
  const s = getSeen();
  ids.forEach((id) => s.add(id));
  try { localStorage.setItem(SEEN_KEY, JSON.stringify([...s].slice(-400))); } catch { /* ignore */ }
}

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
  if (diff < 86400) return i18n.t("stories.timeago_hour", { n: Math.floor(diff / 3600) });
  return `${Math.floor(diff / 86400)}d`;
}

function groupByUser(stories) {
  const map = new Map();
  for (const s of stories) {
    if (!map.has(s.user_id)) map.set(s.user_id, { user_id: s.user_id, author: s.author, is_mine: s.is_mine, stories: [] });
    map.get(s.user_id).stories.push(s);
  }
  const groups = [...map.values()];
  const seen = getSeen();
  groups.forEach((g) => { g.all_seen = g.stories.every((s) => seen.has(s.id)); });
  // mine first, then unseen, then seen (Instagram-like ordering)
  groups.sort((a, b) => {
    if (a.is_mine !== b.is_mine) return a.is_mine ? -1 : 1;
    if (a.all_seen !== b.all_seen) return a.all_seen ? 1 : -1;
    return 0;
  });
  return groups;
}

/* -------------------------------------------------------------------------- */
/* Composer — full-screen, camera first (native feel)                         */
/* -------------------------------------------------------------------------- */
export function AddStoryDialog({ open, onOpenChange, eventId }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const camRef = useRef(null);
  const galRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);

  const reset = useCallback(() => {
    setFile(null);
    setPreview("");
    setCaption("");
  }, []);

  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  const pick = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
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

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[80] bg-black flex flex-col"
        data-testid="story-composer"
      >
        <input ref={camRef} type="file" accept="image/*" capture="environment" hidden onChange={pick} data-testid="story-camera-input" />
        <input ref={galRef} type="file" accept="image/*" hidden onChange={pick} data-testid="story-file-input" />

        {/* top bar */}
        <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-3 pt-[max(12px,env(safe-area-inset-top))] pb-3 bg-gradient-to-b from-black/70 to-transparent">
          <button
            onClick={() => (preview ? reset() : onOpenChange(false))}
            data-testid="story-composer-back"
            className="w-10 h-10 rounded-full bg-white/10 backdrop-blur flex items-center justify-center active:scale-90"
            aria-label="Atrás"
          >
            {preview ? <ChevronLeft className="w-5 h-5 text-white" /> : <X className="w-5 h-5 text-white" />}
          </button>
          <p className="text-white/80 text-xs font-bold uppercase tracking-[0.2em]">{t("stories.add_title")}</p>
          <span className="w-10" />
        </div>

        {preview ? (
          <>
            {/* full-bleed preview */}
            <div className="absolute inset-0">
              <img src={preview} alt="preview" className="w-full h-full object-contain" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/40 pointer-events-none" />
            </div>
            {/* caption + publish */}
            <div className="relative mt-auto z-20 px-4 pb-[max(20px,env(safe-area-inset-bottom))]">
              <input
                data-testid="story-caption"
                placeholder={t("stories.caption_ph")}
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                className="w-full h-12 rounded-2xl bg-black/50 backdrop-blur border border-white/20 px-4 text-white placeholder:text-white/50 outline-none focus:border-qv-primary/60"
              />
              <button
                data-testid="story-submit"
                onClick={submit}
                disabled={busy}
                className="mt-3 w-full h-14 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-white font-display font-black flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60"
              >
                {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                {t("stories.share_with_friends")}
              </button>
              <p className="text-white/45 text-[11px] text-center mt-2">{t("stories.footer_note")}</p>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-qv-primary/30 to-qv-secondary/20 border border-white/15 flex items-center justify-center">
              <Camera className="w-9 h-9 text-white" />
            </div>
            <p className="text-white/60 text-sm text-center leading-relaxed">{t("stories.add_desc")}</p>
            <button
              data-testid="story-take-photo"
              onClick={() => camRef.current?.click()}
              className="w-full max-w-xs h-14 rounded-full bg-white text-black font-display font-black flex items-center justify-center gap-2 active:scale-[0.98]"
            >
              <Camera className="w-5 h-5" /> {t("stories.take_photo", { defaultValue: "Hacer una foto" })}
            </button>
            <button
              data-testid="story-from-gallery"
              onClick={() => galRef.current?.click()}
              className="w-full max-w-xs h-13 py-3.5 rounded-full border border-white/20 bg-white/5 text-white font-bold flex items-center justify-center gap-2 active:scale-[0.98]"
            >
              <Images className="w-5 h-5" /> {t("stories.from_gallery", { defaultValue: "Elegir de la galería" })}
            </button>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
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

/* -------------------------------------------------------------------------- */
/* Viewer — auto-advance, hold to pause, swipe between people                  */
/* -------------------------------------------------------------------------- */
function StoryViewer({ groups, groupIndex, startIndex = 0, onClose }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const [gi, setGi] = useState(groupIndex);
  const [idx, setIdx] = useState(startIndex);
  const [paused, setPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const [reactText, setReactText] = useState("");
  const [typing, setTyping] = useState(false);

  const group = groups[gi];
  const story = group?.stories[idx];
  const isMoment = story?.kind === "moment";

  // mark as seen
  useEffect(() => {
    if (story) markSeen([story.id]);
  }, [story]);

  const nextStory = useCallback(() => {
    setProgress(0);
    const g = groups[gi];
    if (idx < g.stories.length - 1) { setIdx((i) => i + 1); return; }
    if (gi < groups.length - 1) { setGi((x) => x + 1); setIdx(0); return; }
    onClose();
  }, [groups, gi, idx, onClose]);

  const prevStory = useCallback(() => {
    setProgress(0);
    if (idx > 0) { setIdx((i) => i - 1); return; }
    if (gi > 0) {
      const pg = groups[gi - 1];
      setGi((x) => x - 1);
      setIdx(Math.max(0, pg.stories.length - 1));
    }
  }, [groups, gi, idx]);

  // auto-advance timer
  useEffect(() => {
    if (paused || typing || !story) return;
    const started = Date.now();
    const id = setInterval(() => {
      const pct = Math.min(100, ((Date.now() - started) / STORY_MS) * 100);
      setProgress(pct);
      if (pct >= 100) { clearInterval(id); nextStory(); }
    }, 50);
    return () => clearInterval(id);
  }, [paused, typing, story, nextStory]);

  // keyboard
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowRight") nextStory();
      else if (e.key === "ArrowLeft") prevStory();
      else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nextStory, prevStory, onClose]);

  const del = useMutation({
    mutationFn: async () => (await api.delete(`/stories/${story.id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
      qc.invalidateQueries({ queryKey: ["stories-archive"] });
      toast.success(t("stories.toast_deleted"));
      onClose();
    },
  });

  const likeMoment = useMutation({
    mutationFn: async () => (await api.post(`/captures/${story.id}/like`)).data,
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ["stories"] });
      const prev = qc.getQueryData(["stories"]);
      qc.setQueryData(["stories"], (list) =>
        Array.isArray(list)
          ? list.map((x) =>
              x.id === story.id
                ? { ...x, i_liked: !x.i_liked, likes: Math.max(0, (x.likes || 0) + (x.i_liked ? -1 : 1)) }
                : x
            )
          : list
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => { if (ctx?.prev) qc.setQueryData(["stories"], ctx.prev); },
  });

  const react = useMutation({
    mutationFn: async (content) => (await api.post(`/stories/${story.id}/react`, { content })).data,
    onSuccess: () => {
      setReactText("");
      toast.success(t("stories.toast_sent"));
    },
    onError: () => toast.error(t("stories.err_send")),
  });

  if (!story) return null;

  const holdStart = () => setPaused(true);
  const holdEnd = () => setPaused(false);

  return (
    <motion.div
      className="fixed inset-0 z-[90] bg-black select-none"
      data-testid="story-viewer"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        key={`${gi}-${idx}`}
        className="absolute inset-0"
        drag="y"
        dragDirectionLock
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={{ top: 0, bottom: 0.6 }}
        onDragEnd={(_e, info) => { if (info.offset.y > 120) onClose(); }}
        initial={{ opacity: 0, scale: 1.02 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* blurred backdrop so vertical/horizontal photos fill the screen nicely */}
        <div className="absolute inset-0 overflow-hidden">
          <SafeImg src={mediaThumb(story.image_url, 480)} className="w-full h-full object-cover blur-2xl opacity-45 scale-110" />
        </div>
        <div className="absolute inset-0 flex items-center justify-center">
          <SafeImg src={mediaThumb(story.image_url, 1080)} className="max-w-full max-h-full object-contain" />
        </div>

        {/* tap zones: left = back, right = forward, hold = pause */}
        <div className="absolute inset-0 flex" data-testid="story-nav-area">
          <button
            className="w-[32%] h-full"
            aria-label="Anterior"
            data-testid="story-prev"
            onClick={prevStory}
            onPointerDown={holdStart}
            onPointerUp={holdEnd}
            onPointerLeave={holdEnd}
          />
          <button
            className="flex-1 h-full"
            aria-label="Siguiente"
            data-testid="story-next"
            onClick={nextStory}
            onPointerDown={holdStart}
            onPointerUp={holdEnd}
            onPointerLeave={holdEnd}
          />
        </div>

        {/* progress segments */}
        <div className="absolute top-[max(8px,env(safe-area-inset-top))] left-3 right-3 flex gap-1 z-20">
          {group.stories.map((_, i) => (
            <div key={i} className="flex-1 h-[2.5px] rounded-full bg-white/25 overflow-hidden">
              <div
                className="h-full bg-white"
                style={{ width: i < idx ? "100%" : i === idx ? `${progress}%` : "0%", transition: i === idx ? "width 60ms linear" : "none" }}
              />
            </div>
          ))}
        </div>

        {/* header */}
        <div className="absolute top-[max(22px,calc(env(safe-area-inset-top)+14px))] left-3 right-3 flex items-center gap-3 z-20">
          <AvatarCircle name={group.author.name} picture={group.author.picture} size={34} ring={false} />
          <div className="flex-1 min-w-0">
            <p className="text-white font-semibold text-sm truncate drop-shadow">{group.is_mine ? t("stories.your_story") : group.author.name}</p>
            <p className="text-white/70 text-xs">{timeAgo(story.created_at)}</p>
          </div>
          {group.is_mine && !isMoment && (
            <button data-testid="story-delete" onClick={() => del.mutate()} className="w-9 h-9 rounded-full bg-white/10 backdrop-blur flex items-center justify-center active:scale-90">
              <Trash2 className="w-4 h-4 text-white/80" />
            </button>
          )}
          <button data-testid="story-close" onClick={onClose} className="w-9 h-9 rounded-full bg-white/10 backdrop-blur flex items-center justify-center active:scale-90">
            <X className="w-5 h-5 text-white" />
          </button>
        </div>

        {/* bottom layer */}
        <div className="absolute bottom-0 left-0 right-0 z-20 p-4 pb-[max(20px,env(safe-area-inset-bottom))] bg-gradient-to-t from-black/85 via-black/40 to-transparent">
          <div className="flex flex-wrap gap-1.5 mb-2">
            {isMoment && (
              <span className="inline-flex items-center gap-1 qv-glass text-qv-primary text-xs font-bold px-3 py-1 rounded-full border border-qv-primary/30">
                <Zap className="w-3 h-3" /> El Momento
              </span>
            )}
            {story.event_name && (
              <span className="inline-block qv-glass text-white text-xs font-semibold px-3 py-1 rounded-full border border-white/15">
                🎉 {story.event_name}
              </span>
            )}
          </div>
          {story.caption && (
            <p className="text-white text-base leading-snug mb-3" style={{ textShadow: "0 1px 8px rgba(0,0,0,0.8)" }}>
              {story.caption}
            </p>
          )}

          {isMoment ? (
            <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
              <button
                data-testid={`story-moment-like-${story.id}`}
                onClick={() => likeMoment.mutate()}
                disabled={group.is_mine}
                className={`flex items-center gap-2 h-11 px-5 rounded-full font-bold active:scale-95 transition-transform disabled:opacity-70 ${story.i_liked ? "bg-qv-primary text-white" : "bg-white/10 text-white"}`}
              >
                <Heart className="w-5 h-5" fill={story.i_liked ? "currentColor" : "none"} /> {story.likes || 0}
              </button>
              {group.is_mine && <span className="text-white/50 text-xs">{t("stories.your_story")}</span>}
            </div>
          ) : group.is_mine ? (
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
                onFocus={() => setTyping(true)}
                onBlur={() => setTyping(false)}
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
      </motion.div>
    </motion.div>
  );
}

/* -------------------------------------------------------------------------- */
/* Bar                                                                         */
/* -------------------------------------------------------------------------- */
export function StoriesBar() {
  const [addOpen, setAddOpen] = useState(false);
  const [viewer, setViewer] = useState(null); // { groupIndex }
  const { t } = useTranslation();

  const { data: stories = [] } = useQuery({
    queryKey: ["stories"],
    queryFn: async () => (await api.get("/stories")).data,
    refetchInterval: 60000,
  });

  const groups = groupByUser(stories);

  return (
    <>
      <div className="flex overflow-x-auto hide-scrollbar gap-4 px-5 py-2" data-testid="stories-bar">
        {/* Your story — avatar with a + badge (opens camera), tap ring to view yours */}
        <button
          data-testid="add-story-btn"
          onClick={() => setAddOpen(true)}
          className="flex flex-col items-center gap-1.5 shrink-0"
        >
          <div className="relative w-16 h-16 rounded-full border-2 border-dashed border-white/25 flex items-center justify-center bg-white/5">
            <Camera className="w-6 h-6 text-white/70" />
            <span className="absolute -bottom-0.5 -right-0.5 w-6 h-6 rounded-full bg-qv-primary border-2 border-[#0A0A0C] flex items-center justify-center">
              <Plus className="w-3.5 h-3.5 text-white" />
            </span>
          </div>
          <span className="text-[11px] text-white/60 font-medium">{t("stories.your_story")}</span>
        </button>

        {groups.map((g, gIndex) => {
          const hasMoment = g.stories.some((s) => s.kind === "moment");
          const isHighlight = g.stories.length > 0 && g.stories.every((s) => s.is_old);
          const ring = g.all_seen
            ? "bg-white/18"
            : isHighlight
              ? "bg-gradient-to-tr from-white/45 to-white/20"
              : "bg-gradient-to-tr from-qv-primary to-qv-secondary";
          return (
          <button
            key={g.user_id}
            data-testid={`story-bubble-${g.author.username}`}
            onClick={() => setViewer({ groupIndex: gIndex })}
            className="flex flex-col items-center gap-1.5 shrink-0 active:scale-95 transition-transform"
          >
            <div className={`relative w-16 h-16 rounded-full p-[2.5px] ${ring}`}>
              <div className="w-full h-full rounded-full p-[2px] bg-[#0A0A0C]">
                <AvatarCircle name={g.author.name} picture={g.author.picture} size={54} ring={false} className="w-full h-full" />
              </div>
              {hasMoment && (
                <span className={`absolute -bottom-0.5 -right-0.5 w-6 h-6 rounded-full border-2 border-[#0A0A0C] flex items-center justify-center ${isHighlight ? "bg-white/30" : "bg-qv-primary"}`} data-testid={`story-moment-badge-${g.author.username}`}>
                  {isHighlight
                    ? <Star className="w-3 h-3 text-white" fill="currentColor" />
                    : <Zap className="w-3 h-3 text-white" fill="currentColor" />}
                </span>
              )}
            </div>
            <span className={`text-[11px] font-medium truncate max-w-[64px] ${g.all_seen ? "text-white/45" : "text-white/80"}`}>
              {isHighlight ? t("stories.highlight") : (g.is_mine ? t("stories.you") : g.author.name.split(" ")[0])}
            </span>
          </button>
          );
        })}
      </div>

      <AddStoryDialog open={addOpen} onOpenChange={setAddOpen} />
      <AnimatePresence>
        {viewer && (
          <StoryViewer
            groups={groups}
            groupIndex={Math.min(viewer.groupIndex, Math.max(0, groups.length - 1))}
            onClose={() => setViewer(null)}
          />
        )}
      </AnimatePresence>
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
      <AnimatePresence>
        {viewerIdx !== null && myGroup && (
          <StoryViewer
            groups={[myGroup]}
            groupIndex={0}
            startIndex={viewerIdx}
            onClose={() => { setViewerIdx(null); onOpenChange(true); }}
          />
        )}
      </AnimatePresence>
    </>
  );
}
