import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl, mediaThumb, downloadMedia } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Send, Loader2, MoreVertical, LogOut, Camera, Users, X, ImagePlus, Download } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

const LOCALE_BY_LANG = { es: "es-ES", en: "en-GB", de: "de-DE" };
const dateLocale = () => LOCALE_BY_LANG[(i18n.language || "es").slice(0, 2)] || "es-ES";

function msgTime(iso) {
  try { return new Date(iso).toLocaleTimeString(dateLocale(), { hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

/**
 * Universal chat thread — used for both DMs and Group chats.
 * kind: 'dm' | 'group'
 */
export default function ChatThread({ kind }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { t } = useTranslation();
  const scrollRef = useRef(null);
  const photoInputRef = useRef(null);
  const chatPhotoInputRef = useRef(null);
  const [text, setText] = useState("");
  const [showMenu, setShowMenu] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [sendingPhotos, setSendingPhotos] = useState(false);
  const [lightbox, setLightbox] = useState(null);
  const { user: me } = useAuth();

  const messagesKey = kind === "dm" ? ["dm-messages", id] : ["group-messages", id];
  const listEndpoint = kind === "dm" ? `/dm/${id}/messages` : `/groups/${id}/messages`;

  const { data: messages = [], isLoading } = useQuery({
    queryKey: messagesKey,
    queryFn: async () => (await api.get(listEndpoint)).data,
    refetchInterval: 5000,
  });

  const { data: groupInfo } = useQuery({
    queryKey: ["group-info", id],
    queryFn: async () => (await api.get(`/groups/${id}`)).data,
    enabled: kind === "group",
  });

  const { data: photoOp } = useQuery({
    queryKey: ["group-photo-op", id],
    queryFn: async () => (await api.get(`/groups/${id}/photo-op`)).data,
    enabled: kind === "group",
    refetchInterval: 30000,
  });
  const op = photoOp?.active ? photoOp.ops[0] : null;

  const uploadPhoto = useMutation({
    mutationFn: async (file) => {
      const form = new FormData();
      form.append("file", file);
      form.append("event_id", op.event_id);
      return (await api.post(`/groups/${id}/photo`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })).data;
    },
    onSuccess: () => {
      toast.success(t("chat.toast_photo_uploaded"));
      qc.invalidateQueries({ queryKey: messagesKey });
      qc.invalidateQueries({ queryKey: ["group-photo-op", id] });
      setUploadingPhoto(false);
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || t("chat.toast_upload_error"));
      setUploadingPhoto(false);
    },
  });

  const onPhotoPick = (e) => {
    const f = e.target.files?.[0];
    if (!f || !op) return;
    setUploadingPhoto(true);
    uploadPhoto.mutate(f);
    e.target.value = "";
  };

  const { data: friend } = useQuery({
    queryKey: ["user-basic", id],
    queryFn: async () => {
      const friends = (await api.get("/friends")).data;
      return friends.find((f) => f.user_id === id) || null;
    },
    enabled: kind === "dm",
  });

  const send = useMutation({
    mutationFn: async () => {
      const body = text.trim();
      if (kind === "dm") return (await api.post("/dm/send", { to_user_id: id, text: body })).data;
      return (await api.post(`/groups/${id}/messages`, { text: body })).data;
    },
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: messagesKey });
      qc.invalidateQueries({ queryKey: kind === "dm" ? ["dm-threads"] : ["groups"] });
    },
    onError: (err) => toast.error(err.response?.data?.detail || t("chat.toast_send_error")),
  });

  // Attach & send one or more photos inside the chat (DM or group)
  const sendChatPhotos = useMutation({
    mutationFn: async (files) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      const up = (await api.post("/chat/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })).data;
      const urls = (up.uploads || []).map((u) => u.media_url);
      // send one message per photo, in order
      for (const url of urls) {
        if (kind === "dm") {
          await api.post("/dm/send", { to_user_id: id, image_url: url });
        } else {
          await api.post(`/groups/${id}/messages`, { image_url: url });
        }
      }
      return urls.length;
    },
    onSuccess: () => {
      setSendingPhotos(false);
      qc.invalidateQueries({ queryKey: messagesKey });
      qc.invalidateQueries({ queryKey: kind === "dm" ? ["dm-threads"] : ["groups"] });
    },
    onError: (err) => {
      setSendingPhotos(false);
      toast.error(err.response?.data?.detail || t("chat.toast_photo_send_error"));
    },
  });

  const onChatPhotoPick = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    if (files.length > 10) { toast.error(t("chat.max_photos")); e.target.value = ""; return; }
    const tooBig = files.find((f) => f.size > 25 * 1024 * 1024);
    if (tooBig) { toast.error(t("chat.max_size")); e.target.value = ""; return; }
    setSendingPhotos(true);
    sendChatPhotos.mutate(files);
    e.target.value = "";
  };

  const leaveGroup = useMutation({
    mutationFn: async () => (await api.post(`/groups/${id}/leave`)).data,
    onSuccess: () => {
      toast.success(t("chat.toast_left"));
      qc.invalidateQueries({ queryKey: ["groups"] });
      navigate("/chats");
    },
  });

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages.length]);

  // Opening a DM marks its messages read on the backend; refresh the unread
  // badges (bell + chats tab) so the conversation stops showing as pending.
  useEffect(() => {
    if (kind === "dm" && !isLoading) {
      qc.invalidateQueries({ queryKey: ["dm-unread-count"] });
      qc.invalidateQueries({ queryKey: ["unread-count"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["dm-threads"] });
    }
     
  }, [kind, isLoading, messages.length]);

  const title = kind === "dm" ? (friend?.name || t("chat.default_dm")) : (groupInfo?.name || t("chat.default_group"));
  const subtitle = kind === "dm"
    ? (friend?.username ? `@${friend.username}` : "")
    : (groupInfo ? t("chat.members", { count: groupInfo.member_ids.length }) : "");

  return (
    <div className="min-h-screen qv-app-bg flex flex-col">
      <div className="max-w-md mx-auto w-full flex-1 flex flex-col">
        {/* Header */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-white/10 qv-glass sticky top-0 z-20">
          <button
            data-testid="chat-back"
            onClick={() => navigate("/chats")}
            className="w-10 h-10 rounded-full border border-white/15 flex items-center justify-center active:scale-90"
          >
            <ArrowLeft className="w-5 h-5 text-white" />
          </button>
          <button
            onClick={() => kind === "dm" && navigate(`/users/${id}`)}
            className="flex items-center gap-3 flex-1 text-left"
          >
            {kind === "dm" ? (
              <AvatarCircle name={friend?.name || ""} picture={friend?.picture || ""} size={38} ring={false} />
            ) : (
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-qv-primary to-qv-secondary flex items-center justify-center text-white font-black text-sm">
                {title.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <p className="font-bold text-white truncate">{title}</p>
              <p className="text-xs text-white/50 truncate">{subtitle}</p>
            </div>
          </button>
          {kind === "group" && (
            <button
              data-testid="chat-menu"
              onClick={() => setShowMenu(true)}
              className="w-10 h-10 rounded-full border border-white/15 flex items-center justify-center active:scale-90"
            >
              <MoreVertical className="w-5 h-5 text-white" />
            </button>
          )}
        </header>

        {/* Group photo CTA — when 3+ members go to the same party */}
        {kind === "group" && op && (
          <div className="px-4 pt-3" data-testid="group-photo-cta">
            <div className="rounded-2xl border-2 border-qv-secondary/50 bg-gradient-to-br from-qv-secondary/10 via-transparent to-transparent p-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-9 h-9 rounded-full bg-qv-secondary/20 flex items-center justify-center shrink-0">
                  <Users className="w-4.5 h-4.5 text-qv-secondary" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-display font-black text-white text-sm leading-tight">
                    {t("chat.group_photo_title", { count: op.count, event: op.event_name })}
                  </p>
                  <p className="text-white/50 text-xs truncate">{t("chat.group_photo_sub")}</p>
                </div>
                <div className="flex -space-x-2 shrink-0">
                  {(op.members_going || []).slice(0, 3).map((m, i) => (
                    <AvatarCircle key={i} name={m.name} picture={m.picture} size={24} />
                  ))}
                </div>
              </div>
              <button
                data-testid="group-photo-btn"
                onClick={() => photoInputRef.current?.click()}
                disabled={uploadingPhoto}
                className="w-full h-11 rounded-xl bg-qv-secondary text-black font-bold text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
              >
                {uploadingPhoto ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> {t("chat.uploading")}</>
                ) : (
                  <><Camera className="w-4 h-4" /> {op.i_uploaded ? t("chat.upload_another") : t("chat.take_group_photo")}</>
                )}
              </button>
              {op.photos_count > 0 && (
                <p className="text-center text-white/40 text-[11px] mt-1.5">
                  {t(op.photos_count === 1 ? "chat.photos_in_chat_one" : "chat.photos_in_chat_other", { count: op.photos_count })}
                </p>
              )}
            </div>
            <input
              ref={photoInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={onPhotoPick}
              className="hidden"
              data-testid="group-photo-input"
            />
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto hide-scrollbar px-4 py-4 flex flex-col gap-3" data-testid="chat-messages">
          {isLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
          ) : messages.length === 0 ? (
            <p className="text-center text-white/40 text-sm py-10">{t("chat.empty")}</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={`flex gap-2 ${m.is_mine ? "flex-row-reverse" : ""}`} data-testid={`msg-${m.id}`}>
                {!m.is_mine && kind === "group" && (
                  <AvatarCircle name={m.author?.name || ""} picture={m.author?.picture || ""} size={28} ring={false} />
                )}
                <div className={`max-w-[75%] ${m.is_mine ? "items-end" : "items-start"} flex flex-col`}>
                  <div className={`rounded-2xl px-3 py-2 text-sm ${m.is_mine ? "bg-qv-primary text-white" : "bg-white/10 text-white"}`}>
                    {!m.is_mine && kind === "group" && (
                      <span className="block text-[11px] text-qv-secondary font-semibold">{m.author?.name?.split(" ")[0]}</span>
                    )}
                    {m.image_url && (
                      <button
                        onClick={() => setLightbox(m.image_url)}
                        className="block mb-1 rounded-xl overflow-hidden active:scale-[0.98]"
                        data-testid={`msg-photo-${m.id}`}
                      >
                        <img src={mediaThumb(m.image_url, 500)} alt="Foto" className="w-48 max-w-full rounded-xl" loading="lazy" />
                      </button>
                    )}
                    {m.text}
                  </div>
                  <span className="text-[10px] text-white/40 mt-0.5 px-1">{msgTime(m.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Input */}
        <div className="px-4 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] border-t border-white/10 qv-glass sticky bottom-0 flex items-center gap-2">
          <button
            data-testid="chat-attach"
            onClick={() => chatPhotoInputRef.current?.click()}
            disabled={sendingPhotos}
            className="w-11 h-11 rounded-full bg-white/5 border border-white/15 flex items-center justify-center shrink-0 active:scale-90 disabled:opacity-40"
            title={t("chat.attach_title")}
          >
            {sendingPhotos ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <ImagePlus className="w-5 h-5 text-white/80" />}
          </button>
          <input
            ref={chatPhotoInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={onChatPhotoPick}
            className="hidden"
            data-testid="chat-photo-input"
          />
          <Input
            data-testid="chat-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) send.mutate(); }}
            placeholder={t("chat.input_ph")}
            className="flex-1 h-11 bg-white/5 border-white/15 rounded-full text-white placeholder:text-white/40"
          />
          <button
            data-testid="chat-send"
            onClick={() => text.trim() && send.mutate()}
            disabled={send.isPending || !text.trim()}
            className="w-11 h-11 rounded-full bg-qv-primary flex items-center justify-center shrink-0 active:scale-90 disabled:opacity-40"
          >
            <Send className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>

      <Dialog open={showMenu} onOpenChange={setShowMenu}>
        <DialogContent className="bg-[#121215] border-white/10 text-white max-w-sm rounded-2xl">
          <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {groupInfo?.members?.map((m) => (
              <div key={m.user_id} className="flex items-center gap-3">
                <AvatarCircle name={m.name} picture={m.picture} size={34} ring={false} />
                <span className="flex-1 text-white text-sm">{m.name}</span>
                {groupInfo?.created_by === m.user_id && <span className="text-[10px] uppercase text-qv-secondary font-bold">{t("chat.creator")}</span>}
                {m.user_id === me?.user_id && <span className="text-[10px] uppercase text-white/40 font-bold">{t("chat.you")}</span>}
              </div>
            ))}
          </div>
          <button
            data-testid="leave-group"
            onClick={() => leaveGroup.mutate()}
            className="h-11 rounded-2xl bg-red-500/20 text-red-300 font-bold flex items-center justify-center gap-2"
          >
            <LogOut className="w-4 h-4" /> {t("chat.leave")}
          </button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!lightbox} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="bg-black border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden">
          {lightbox && (
            <div className="relative">
              <button
                onClick={() => setLightbox(null)}
                className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center"
              >
                <X className="w-5 h-5 text-white" />
              </button>
              <button
                type="button"
                data-testid="chat-photo-download"
                onClick={() => downloadMedia(lightbox)}
                className="absolute top-3 left-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center"
                title={t("chat.download_title")}
              >
                <Download className="w-4 h-4 text-white" />
              </button>
              <img src={mediaThumb(lightbox, 1200)} alt="Foto" className="w-full max-h-[80vh] object-contain" />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
