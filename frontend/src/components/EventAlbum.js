import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api, { mediaUrl, mediaThumb, downloadMedia, shareMedia } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import {
  Plus, Play, Trash2, Images, Loader2, X, Share2, Lock, Users, Check, Globe,
  Download, CheckCircle2, Circle,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ReportFlag } from "@/components/ReportBlock";
import { toast } from "sonner";

/**
 * Event album — PRIVATE by default.
 * "Mías": your own uploads, only you see them until you share.
 * "Compartido": the combined album = photos you shared + photos friends/groups shared with you.
 * Supports MULTI upload (several files at once) and MULTI share (select many, share once).
 */
export function EventAlbum({ eventId, hasInterest, prominent = false }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const inputRef = useRef(null);
  const [tab, setTab] = useState("mias");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [preview, setPreview] = useState(null);
  const [shareFor, setShareFor] = useState(null); // single upload being shared
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [shareBatch, setShareBatch] = useState(null); // array of upload ids

  const { data, isLoading } = useQuery({
    queryKey: ["album", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/album`)).data,
    retry: false,
  });

  const uploadMut = useMutation({
    mutationFn: async (files) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return (await api.post(`/events/${eventId}/album/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => { if (e.total) setProgress(Math.round((e.loaded / e.total) * 100)); },
      })).data;
    },
    onSuccess: (res) => {
      const n = res?.count || 1;
      toast.success(t("album.toast_saved", { count: n }));
      qc.invalidateQueries({ queryKey: ["album", eventId] });
      qc.invalidateQueries({ queryKey: ["badges", "me"] });
      setUploading(false); setProgress(0);
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || t("album.toast_upload_error"));
      setUploading(false); setProgress(0);
    },
  });

  const deleteMut = useMutation({
    mutationFn: async (uploadId) => (await api.delete(`/events/${eventId}/album/${uploadId}`)).data,
    onSuccess: () => {
      toast.success(t("album.toast_deleted"));
      qc.invalidateQueries({ queryKey: ["album", eventId] });
      setPreview(null);
    },
  });

  const unshareMut = useMutation({
    mutationFn: async (uploadId) => (await api.post(`/events/${eventId}/album/${uploadId}/unshare`)).data,
    onSuccess: () => {
      toast.success(t("album.toast_unshared"));
      qc.invalidateQueries({ queryKey: ["album", eventId] });
      setPreview(null);
    },
  });

  const onPick = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const tooBig = files.find((f) => f.size > 50 * 1024 * 1024);
    if (tooBig) { toast.error(t("album.err_too_big")); e.target.value = ""; return; }
    if (files.length > 30) { toast.error(t("album.err_too_many")); e.target.value = ""; return; }
    setUploading(true);
    uploadMut.mutate(files);
    e.target.value = "";
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const exitSelect = () => { setSelectMode(false); setSelected(new Set()); };

  if (isLoading) return null;
  if (!data) return <div className="text-white/40 text-xs italic">{t("album.need_interest")}</div>;

  const mine = data.mine || [];
  const shared = data.shared || [];
  const canUpload = data.can_upload && hasInterest;
  const items = tab === "mias" ? mine : shared;

  return (
    <div className={prominent ? "rounded-3xl border border-qv-secondary/30 bg-gradient-to-br from-qv-secondary/10 via-white/[0.03] to-transparent p-4" : ""}>
      {prominent && (
        <div className="flex items-start gap-3 mb-3">
          <div className="w-11 h-11 rounded-2xl bg-qv-secondary/20 flex items-center justify-center shrink-0">
            <Images className="w-5 h-5 text-qv-secondary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-display font-black text-white text-lg leading-tight">{t("album.header_title")}</p>
            <p className="text-white/55 text-xs leading-snug mt-0.5">
              {t("album.header_sub")}
            </p>
          </div>
          {canUpload && (
            <button
              data-testid="album-prominent-upload"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="shrink-0 h-9 px-3 rounded-full bg-qv-secondary text-black text-xs font-bold flex items-center gap-1 active:scale-95 disabled:opacity-60"
            >
              {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Plus className="w-4 h-4" /> {t("album.upload")}</>}
            </button>
          )}
        </div>
      )}
      <div className="flex items-center justify-between mb-2">
        <p className="flex items-center gap-2 text-xs uppercase tracking-widest text-white/40 font-bold">
          <Images className="w-4 h-4 text-qv-secondary" /> {t("album.album")}
        </p>
        {tab === "mias" && mine.length > 0 && (
          selectMode ? (
            <button
              data-testid="album-select-cancel"
              onClick={exitSelect}
              className="text-xs font-bold text-white/60"
            >
              {t("album.cancel")}
            </button>
          ) : (
            <button
              data-testid="album-select-mode"
              onClick={() => setSelectMode(true)}
              className="text-xs font-bold text-qv-secondary flex items-center gap-1"
            >
              <CheckCircle2 className="w-3.5 h-3.5" /> {t("album.select")}
            </button>
          )
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1.5 mb-3 p-1 rounded-2xl bg-white/5 border border-white/10">
        <button
          data-testid="album-tab-mias"
          onClick={() => { setTab("mias"); }}
          className={`flex-1 py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors ${tab === "mias" ? "bg-white text-black" : "text-white/60"}`}
        >
          <Lock className="w-3.5 h-3.5" /> {t("album.tab_mine")} <span className="opacity-60">({mine.length})</span>
        </button>
        <button
          data-testid="album-tab-shared"
          onClick={() => { setTab("compartido"); exitSelect(); }}
          className={`flex-1 py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors ${tab === "compartido" ? "bg-white text-black" : "text-white/60"}`}
        >
          <Users className="w-3.5 h-3.5" /> {t("album.tab_shared")} <span className="opacity-60">({shared.length})</span>
        </button>
      </div>

      {tab === "mias" && !selectMode && (
        <p className="text-white/40 text-[11px] mb-2 flex items-center gap-1">
          <Lock className="w-3 h-3" /> {t("album.private_note")}
        </p>
      )}
      {selectMode && (
        <p className="text-qv-secondary text-[11px] mb-2 font-semibold">
          {t("album.select_note", { count: selected.size })}
        </p>
      )}

      {items.length === 0 && tab === "mias" ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-6 text-center">
          <Images className="w-8 h-8 text-white/30 mx-auto mb-2" />
          <p className="text-white/50 text-sm mb-3">{t("album.empty_mine")}</p>
          {canUpload && (
            <button
              data-testid="album-empty-upload"
              onClick={() => inputRef.current?.click()}
              className="h-10 px-4 rounded-full bg-qv-primary text-white font-bold text-sm active:scale-95"
            >
              <Plus className="w-4 h-4 inline mr-1" /> {t("album.upload_yours")}
            </button>
          )}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-6 text-center">
          <Users className="w-8 h-8 text-white/30 mx-auto mb-2" />
          <p className="text-white/50 text-sm">{t("album.empty_shared")}</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-1.5" data-testid="album-grid">
          {tab === "mias" && canUpload && !selectMode && (
            <button
              data-testid="album-add-btn"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="aspect-square rounded-xl border border-dashed border-white/25 bg-white/[0.03] flex flex-col items-center justify-center text-white/60 active:scale-95 disabled:opacity-50"
            >
              {uploading ? (
                <><Loader2 className="w-5 h-5 animate-spin" /><span className="text-[10px] mt-1">{progress}%</span></>
              ) : (
                <><Plus className="w-6 h-6" /><span className="text-[10px] mt-1">{t("album.upload_several")}</span></>
              )}
            </button>
          )}
          {items.map((it) => {
            const isSel = selected.has(it.id);
            return (
              <button
                key={it.id}
                onClick={() => (selectMode ? toggleSelect(it.id) : setPreview(it))}
                data-testid={`album-item-${it.id}`}
                className={`aspect-square rounded-xl overflow-hidden bg-black relative active:scale-95 ${isSel ? "ring-2 ring-qv-secondary" : ""}`}
              >
                {it.media_type === "video" ? (
                  <>
                    <video src={mediaUrl(it.media_url)} className="w-full h-full object-cover" muted playsInline preload="metadata" />
                    <div className="absolute inset-0 flex items-center justify-center"><Play className="w-8 h-8 text-white drop-shadow-lg" fill="white" /></div>
                  </>
                ) : (
                  <img src={mediaThumb(it.media_url, 400)} alt="" className="w-full h-full object-cover" loading="lazy" />
                )}
                {/* selection indicator */}
                {selectMode && (
                  <div className="absolute top-1 left-1">
                    {isSel ? (
                      <CheckCircle2 className="w-5 h-5 text-qv-secondary drop-shadow" fill="currentColor" />
                    ) : (
                      <Circle className="w-5 h-5 text-white/80 drop-shadow" />
                    )}
                  </div>
                )}
                {/* status badge */}
                {tab === "mias" && !selectMode && (
                  <div className="absolute top-1 right-1">
                    {it.shared ? (
                      <span className="bg-qv-secondary text-black text-[9px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5"><Users className="w-2.5 h-2.5" /></span>
                    ) : (
                      <span className="bg-black/60 text-white/80 text-[9px] font-bold p-1 rounded-full flex items-center"><Lock className="w-2.5 h-2.5" /></span>
                    )}
                  </div>
                )}
                {tab === "compartido" && !it.is_mine && (
                  <div className="absolute bottom-1 left-1 flex items-center gap-1">
                    <AvatarCircle name={it.author?.name || ""} picture={it.author?.picture || ""} size={18} ring={false} />
                  </div>
                )}
                {tab === "compartido" && !it.is_mine && (
                  <div className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/50 flex items-center justify-center">
                    <ReportFlag targetType="album_photo" targetId={it.id} />
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Sticky action bar when selecting */}
      {selectMode && selected.size > 0 && (
        <div className="sticky bottom-2 mt-3 z-20">
          <button
            data-testid="album-share-selected"
            onClick={() => setShareBatch(Array.from(selected))}
            className="w-full py-3 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-95 shadow-lg"
          >
            <Share2 className="w-4 h-4" /> {t("album.share_n", { count: selected.size })}
          </button>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*,video/*"
        multiple
        onChange={onPick}
        className="hidden"
        data-testid="album-file-input"
      />

      {/* Preview dialog */}
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="bg-black border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden">
          {preview && (
            <div className="relative">
              <button onClick={() => setPreview(null)} className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center">
                <X className="w-5 h-5 text-white" />
              </button>
              {preview.media_type === "video" ? (
                <video src={mediaUrl(preview.media_url)} controls autoPlay className="w-full max-h-[62vh]" />
              ) : (
                <img src={mediaThumb(preview.media_url, 1200)} alt="" className="w-full max-h-[62vh] object-contain" />
              )}
              <div className="p-4 flex items-center gap-3">
                <AvatarCircle name={preview.author?.name || ""} picture={preview.author?.picture || ""} size={32} ring={false} />
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-semibold truncate">{preview.author?.name}</p>
                  <p className="text-white/40 text-xs">{new Date(preview.created_at).toLocaleString("es-ES")}</p>
                </div>
                <button
                  type="button"
                  data-testid="album-download-btn"
                  onClick={() => downloadMedia(preview.media_url)}
                  className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center active:scale-95"
                  title={t("album.download_full")}
                >
                  <Download className="w-4 h-4 text-white/80" />
                </button>
                {preview.media_type !== "video" && (
                  <button
                    type="button"
                    data-testid="album-share-native-btn"
                    onClick={async () => {
                      const r = await shareMedia(preview.media_url, { title: t("album.photo_title"), text: t("album.photo_text") });
                      if (r === "downloaded") toast.success(t("album.toast_downloaded"));
                    }}
                    className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center active:scale-95"
                    title={t("album.share")}
                  >
                    <Share2 className="w-4 h-4 text-white/80" />
                  </button>
                )}
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
              {preview.is_mine && (
                <div className="px-4 pb-4 flex items-center gap-2">
                  <button
                    data-testid="album-share-btn"
                    onClick={() => { setShareFor(preview); }}
                    className="flex-1 py-3 rounded-2xl bg-qv-primary text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-95"
                  >
                    <Share2 className="w-4 h-4" /> {preview.shared ? t("album.edit_who") : t("album.share")}
                  </button>
                  {preview.shared && (
                    <button
                      onClick={() => unshareMut.mutate(preview.id)}
                      disabled={unshareMut.isPending}
                      className="py-3 px-4 rounded-2xl bg-white/10 text-white/80 font-bold text-sm active:scale-95"
                    >
                      {t("album.unshare")}
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {shareFor && (
        <SharePicker
          eventId={eventId}
          upload={shareFor}
          onClose={() => setShareFor(null)}
          onDone={() => { setShareFor(null); setPreview(null); qc.invalidateQueries({ queryKey: ["album", eventId] }); }}
        />
      )}

      {shareBatch && (
        <SharePicker
          eventId={eventId}
          uploadIds={shareBatch}
          onClose={() => setShareBatch(null)}
          onDone={() => { setShareBatch(null); exitSelect(); qc.invalidateQueries({ queryKey: ["album", eventId] }); }}
        />
      )}
    </div>
  );
}

function SharePicker({ eventId, upload, uploadIds, onClose, onDone }) {
  const { t } = useTranslation();
  const isBatch = Array.isArray(uploadIds);
  const [selUsers, setSelUsers] = useState(new Set(upload?.shared_with_users || []));
  const [selGroups, setSelGroups] = useState(new Set(upload?.shared_with_groups || []));
  const [allFriends, setAllFriends] = useState(!!upload?.shared_all_friends);

  const { data: friends = [] } = useQuery({
    queryKey: ["friends"],
    queryFn: async () => (await api.get("/friends")).data,
  });
  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: async () => (await api.get("/groups")).data,
  });

  const shareMut = useMutation({
    mutationFn: async () => {
      const audience = {
        user_ids: Array.from(selUsers),
        group_ids: Array.from(selGroups),
        all_friends: allFriends,
      };
      if (isBatch) {
        return (await api.post(`/events/${eventId}/album/share-batch`, {
          upload_ids: uploadIds,
          ...audience,
        })).data;
      }
      return (await api.post(`/events/${eventId}/album/${upload.id}/share`, audience)).data;
    },
    onSuccess: () => {
      toast.success(isBatch ? t("album.toast_shared_batch", { count: uploadIds.length }) : t("album.toast_shared_single"));
      onDone();
    },
    onError: (e) => toast.error(e.response?.data?.detail || t("album.toast_share_error")),
  });

  const toggle = (set, setter, id) => {
    const n = new Set(set);
    if (n.has(id)) n.delete(id); else n.add(id);
    setter(n);
  };

  const nothingSelected = !allFriends && selUsers.size === 0 && selGroups.size === 0;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-[#0d0d0d] border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden max-h-[85vh] flex flex-col">
        <div className="p-4 border-b border-white/10">
          <h3 className="font-display font-black text-lg">
            {isBatch ? t("album.share_n", { count: uploadIds.length }) : t("album.with_whom")}
          </h3>
          <p className="text-white/50 text-xs mt-0.5">{isBatch ? t("album.only_chosen_batch") : t("album.only_chosen_single")}</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <button
            data-testid="share-all-friends"
            onClick={() => setAllFriends((v) => !v)}
            className={`w-full flex items-center gap-3 p-3 rounded-2xl border transition-colors ${allFriends ? "bg-qv-primary/15 border-qv-primary/50" : "bg-white/5 border-white/10"}`}
          >
            <div className="w-9 h-9 rounded-full bg-qv-primary/20 flex items-center justify-center"><Globe className="w-4.5 h-4.5 text-qv-primary" /></div>
            <span className="flex-1 text-left font-semibold text-sm">{t("album.all_friends")}</span>
            {allFriends && <Check className="w-5 h-5 text-qv-primary" />}
          </button>

          {groups.length > 0 && (
            <div>
              <p className="text-white/40 text-[11px] uppercase tracking-widest font-bold mb-2">{t("album.groups")}</p>
              <div className="space-y-1.5">
                {groups.map((g) => {
                  const on = selGroups.has(g.id);
                  return (
                    <button
                      key={g.id}
                      data-testid={`share-group-${g.id}`}
                      onClick={() => toggle(selGroups, setSelGroups, g.id)}
                      className={`w-full flex items-center gap-3 p-2.5 rounded-2xl border transition-colors ${on ? "bg-qv-secondary/15 border-qv-secondary/50" : "bg-white/5 border-white/10"}`}
                    >
                      <div className="w-9 h-9 rounded-full bg-qv-secondary/20 flex items-center justify-center"><Users className="w-4 h-4 text-qv-secondary" /></div>
                      <span className="flex-1 text-left font-semibold text-sm truncate">{g.name}<span className="text-white/40 font-normal"> · {g.member_ids?.length || 0}</span></span>
                      {on && <Check className="w-5 h-5 text-qv-secondary" />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <p className="text-white/40 text-[11px] uppercase tracking-widest font-bold mb-2">{t("album.friends")}</p>
            {friends.length === 0 ? (
              <p className="text-white/40 text-xs">{t("album.no_friends")}</p>
            ) : (
              <div className="space-y-1.5">
                {friends.map((f) => {
                  const on = selUsers.has(f.user_id);
                  return (
                    <button
                      key={f.user_id}
                      data-testid={`share-friend-${f.user_id}`}
                      onClick={() => toggle(selUsers, setSelUsers, f.user_id)}
                      disabled={allFriends}
                      className={`w-full flex items-center gap-3 p-2.5 rounded-2xl border transition-colors disabled:opacity-40 ${on ? "bg-qv-primary/15 border-qv-primary/50" : "bg-white/5 border-white/10"}`}
                    >
                      <AvatarCircle name={f.name} picture={f.picture} size={36} ring={false} />
                      <span className="flex-1 text-left font-semibold text-sm truncate">{f.name}</span>
                      {(on || allFriends) && <Check className="w-5 h-5 text-qv-primary" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="p-4 border-t border-white/10 flex gap-2">
          <button onClick={onClose} className="py-3 px-4 rounded-2xl bg-white/10 text-white/80 font-bold text-sm active:scale-95">{t("album.cancel")}</button>
          <button
            data-testid="share-confirm"
            onClick={() => shareMut.mutate()}
            disabled={nothingSelected || shareMut.isPending}
            className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-50"
          >
            {shareMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />} {t("album.share")}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
