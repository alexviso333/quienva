import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api, { mediaThumb, mediaUrl, downloadMedia, shareMedia } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { ReportFlag } from "@/components/ReportBlock";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Zap, Camera, Timer, Download, Share2, X } from "lucide-react";
import { toast } from "@/lib/notify";

/**
 * "El Momento" — our own take on the BeReal-style capture during a party.
 * Admin triggers the prompt; users have 2 minutes to upload for on-time points.
 * After uploading, users can see their friends' captures side-by-side.
 */
export function EventMoment({ eventId, hasInterest, past = false }) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [secLeft, setSecLeft] = useState(null);
  const [preview, setPreview] = useState(null);

  const { data: status } = useQuery({
    queryKey: ["moment-status", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/moment/status`)).data,
    refetchInterval: 15000,
    retry: false,
  });

  const { data: gallery = [] } = useQuery({
    queryKey: ["moment-gallery", eventId],
    queryFn: async () => (await api.get(`/events/${eventId}/moment/gallery`)).data,
    enabled: !!status?.my_capture,
    refetchInterval: 15000,
    retry: false,
  });

  // Countdown to on_time_deadline
  useEffect(() => {
    if (!status?.prompt?.on_time_deadline || status?.my_capture) {
      setSecLeft(null);
      return;
    }
    const tick = () => {
      const deadline = new Date(status.prompt.on_time_deadline).getTime();
      const now = Date.now();
      const sec = Math.max(0, Math.round((deadline - now) / 1000));
      setSecLeft(sec);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [status?.prompt?.on_time_deadline, status?.my_capture]);

  if (!hasInterest) return null;

  // Memories mode (past party): show ONLY the gallery of moments captured that
  // night, next to the shared album. No capture CTA. If I didn't capture, there's
  // nothing of mine to show, so render nothing.
  if (past && !status?.my_capture) return null;

  // No active prompt yet
  if (!status?.prompt) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-yellow-300/15 flex items-center justify-center">
            <Zap className="w-5 h-5 text-yellow-300" />
          </div>
          <div>
            <p className="font-bold text-white">{t("eventmoment.title")}</p>
            <p className="text-white/50 text-xs">{t("eventmoment.prepare")}</p>
          </div>
        </div>
      </div>
    );
  }

  // Already uploaded — show gallery
  if (status.my_capture) {
    return (
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-widest text-white/40 font-bold mb-2">
          <Zap className="w-4 h-4 text-yellow-300" /> {t("eventmoment.title")}
          {status.my_capture.on_time && (
            <span className="text-yellow-300 font-bold">{t("eventmoment.on_time_badge")}</span>
          )}
        </p>
        <div className="grid grid-cols-3 gap-1.5" data-testid="moment-gallery">
          {gallery.map((c) => (
            <div
              key={c.id}
              onClick={() => setPreview(c)}
              data-testid={`moment-item-${c.id}`}
              className="aspect-square rounded-xl overflow-hidden bg-black relative cursor-pointer active:scale-95 transition-transform"
            >
              <img src={mediaThumb(c.image_url, 500)} alt="" className="w-full h-full object-cover" loading="lazy" />
              <div className="absolute bottom-1 left-1 flex items-center gap-1 bg-black/50 rounded-full px-1.5 py-0.5">
                <AvatarCircle name={c.author?.name || ""} picture={c.author?.picture || ""} size={16} ring={false} />
                <span className="text-white text-[10px] font-bold">{c.author?.name?.split(" ")[0]}</span>
              </div>
              {c.on_time && (
                <div className="absolute top-1 right-1 bg-yellow-300 text-black text-[9px] font-bold px-1.5 py-0.5 rounded-full">{t("eventmoment.on_time_tag")}</div>
              )}
              {!c.is_mine && (
                <div
                  className="absolute top-1 left-1 w-6 h-6 rounded-full bg-black/50 flex items-center justify-center"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ReportFlag targetType="moment" targetId={c.id} />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Viewer with download + share (great for saving your Momento memory) */}
        <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
          <DialogContent className="bg-black border-white/10 text-white max-w-md rounded-2xl p-0 overflow-hidden">
            {preview && (
              <div className="relative">
                <button onClick={() => setPreview(null)} className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center">
                  <X className="w-5 h-5 text-white" />
                </button>
                <img src={mediaUrl(preview.image_url)} alt="" className="w-full max-h-[62vh] object-contain" />
                <div className="p-4 flex items-center gap-3">
                  <AvatarCircle name={preview.author?.name || ""} picture={preview.author?.picture || ""} size={32} ring={false} />
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-semibold truncate">{preview.author?.name}</p>
                    <p className="text-white/40 text-xs">{t("eventmoment.title")}</p>
                  </div>
                  <button
                    type="button"
                    data-testid="moment-download-btn"
                    onClick={() => downloadMedia(preview.image_url, `momento-${preview.id}.jpg`)}
                    className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center active:scale-95"
                    title={t("eventmoment.download")}
                  >
                    <Download className="w-4 h-4 text-white/80" />
                  </button>
                  <button
                    type="button"
                    data-testid="moment-share-btn"
                    onClick={async () => {
                      const r = await shareMedia(preview.image_url, { title: t("eventmoment.share_title"), text: t("eventmoment.share_text"), filename: `momento-${preview.id}.jpg` });
                      if (r === "downloaded") toast.success(t("eventmoment.toast_downloaded"));
                    }}
                    className="w-10 h-10 rounded-full bg-yellow-300 flex items-center justify-center active:scale-95"
                    title={t("eventmoment.share")}
                  >
                    <Share2 className="w-4 h-4 text-black" />
                  </button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // Prompt active but not uploaded — show camera CTA + countdown
  const isOnTimeStill = secLeft !== null && secLeft > 0;
  return (
    <div className="rounded-2xl border-2 border-yellow-300/50 bg-gradient-to-br from-yellow-300/10 via-transparent to-transparent p-4 animate-pulse-slow" data-testid="moment-active">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-12 h-12 rounded-full bg-yellow-300/20 flex items-center justify-center">
          <Zap className="w-6 h-6 text-yellow-300" />
        </div>
        <div className="flex-1">
          <p className="font-display font-black text-white text-lg leading-none">{t("eventmoment.active_title")}</p>
          <p className="text-yellow-200/80 text-xs">{t("eventmoment.active_sub")}</p>
        </div>
      </div>
      {isOnTimeStill ? (
        <div className="flex items-center gap-2 mb-3 justify-center">
          <Timer className="w-4 h-4 text-yellow-300" />
          <span className="font-display text-3xl font-black text-yellow-300 tabular-nums">
            {Math.floor(secLeft / 60)}:{String(secLeft % 60).padStart(2, "0")}
          </span>
        </div>
      ) : (
        <p className="text-center text-white/60 text-xs mb-3">{t("eventmoment.bonus_over")}</p>
      )}
      <button
        data-testid="moment-capture-btn"
        onClick={() => navigate("/momento")}
        className="w-full h-12 rounded-2xl bg-yellow-300 text-black font-bold flex items-center justify-center gap-2 active:scale-95"
      >
        <Camera className="w-5 h-5" /> {t("eventmoment.take_photo")}
      </button>
    </div>
  );
}
