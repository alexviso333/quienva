import { useState } from "react";
import { useTranslation } from "react-i18next";
import { mediaThumb, mediaUrl } from "@/lib/api";
import { formatPartyDate } from "@/lib/format";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Sparkles, Share2, Download, Loader2, Users } from "lucide-react";
import { toast } from "@/lib/notify";

/**
 * "Repaso de la noche" — a shareable recap card for a PAST party.
 * Shows the poster, name, date and the friends you coincided with, and can
 * export a 1080x1920 image (Instagram-story size) to share or download.
 */
export function NightRecapCard({ event }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const friends = event?.friends_attended || [];
  const nFriends = friends.length;

  // Fit `src` over the rect as "cover".
  const drawCover = (ctx, src, dx, dy, dw, dh) => {
    const sr = src.width / src.height;
    const tr = dw / dh;
    let sw, sh, sx, sy;
    if (sr > tr) { sh = src.height; sw = sh * tr; sx = (src.width - sw) / 2; sy = 0; }
    else { sw = src.width; sh = sw / tr; sx = 0; sy = (src.height - sh) / 2; }
    ctx.drawImage(src, sx, sy, sw, sh, dx, dy, dw, dh);
  };

  const wrap = (ctx, text, x, y, maxW, lh, maxLines = 3) => {
    const words = (text || "").split(" ");
    let line = "";
    let lines = [];
    for (const w of words) {
      const test = line ? `${line} ${w}` : w;
      if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; }
      else line = test;
    }
    if (line) lines.push(line);
    lines = lines.slice(0, maxLines);
    lines.forEach((l, i) => ctx.fillText(l, x, y + i * lh));
    return y + lines.length * lh;
  };

  const buildImage = async () => {
    const W = 1080, H = 1920;
    const canvas = document.createElement("canvas");
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext("2d");
    // Background
    ctx.fillStyle = "#0a0a0f";
    ctx.fillRect(0, 0, W, H);
    // Poster (top portion)
    if (event.image_url) {
      try {
        const res = await fetch(mediaThumb(event.image_url, 1080), { mode: "cors" });
        const blob = await res.blob();
        const bmp = await createImageBitmap(blob);
        drawCover(ctx, bmp, 0, 0, W, Math.round(H * 0.66));
      } catch (_e) { /* keep solid bg */ }
    }
    // Gradient for legibility
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "rgba(0,0,0,0.15)");
    g.addColorStop(0.5, "rgba(10,10,15,0.55)");
    g.addColorStop(0.72, "rgba(10,10,15,0.96)");
    g.addColorStop(1, "#0a0a0f");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    // Label
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#FFD400";
    ctx.font = "800 42px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    ctx.fillText(t("nightrecap.img_label"), 80, Math.round(H * 0.70));
    // Title
    ctx.fillStyle = "#ffffff";
    ctx.font = "900 96px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    let y = wrap(ctx, event.name || "", 80, Math.round(H * 0.70) + 96, W - 160, 100, 3);
    // Date + venue
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    ctx.font = "500 40px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    const dline = [formatPartyDate(event.date, event.time), event.venue].filter(Boolean).join("  ·  ");
    y = wrap(ctx, dline, 80, y + 20, W - 160, 50, 2);
    // Friends coincided
    if (nFriends > 0) {
      ctx.fillStyle = "#FF2E7E";
      ctx.font = "800 46px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
      const names = friends.slice(0, 3).map((f) => (f.name || "").split(" ")[0]).filter(Boolean).join(", ");
      const extra = nFriends > 3 ? ` +${nFriends - 3}` : "";
      const line = t("nightrecap.coincided", { count: nFriends });
      ctx.fillText(line, 80, y + 60);
      if (names) {
        ctx.fillStyle = "rgba(255,255,255,0.7)";
        ctx.font = "500 38px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
        ctx.fillText(`${names}${extra}`, 80, y + 118);
      }
    }
    // Watermark
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.font = "900 46px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    ctx.fillText("¿Quién va?", 80, H - 70);
    return await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.92));
  };

  const shareOrDownload = async (mode) => {
    if (busy) return;
    setBusy(true);
    try {
      const blob = await buildImage();
      if (!blob) throw new Error("no blob");
      const file = new File([blob], `repaso-${event.id}.jpg`, { type: "image/jpeg" });
      if (mode === "share" && navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: event.name, text: t("nightrecap.share_text", { name: event.name }) });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `repaso-${event.id}.jpg`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        if (mode === "share") toast.success(t("nightrecap.toast_saved"));
      }
    } catch (e) {
      if (!(e && e.name === "AbortError")) toast.error(t("nightrecap.toast_error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="rounded-3xl overflow-hidden border border-white/10 bg-gradient-to-br from-qv-primary/15 via-white/[0.03] to-qv-secondary/10"
      data-testid="night-recap-card"
    >
      <div className="relative h-40">
        {event.image_url ? (
          <img src={mediaUrl(event.image_url)} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-[#2a0a1a] to-[#0a1a1f]" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
        <div className="absolute bottom-3 left-4 right-4">
          <p className="flex items-center gap-1.5 text-yellow-300 font-black text-[11px] uppercase tracking-widest">
            <Sparkles className="w-3.5 h-3.5" /> {t("nightrecap.eyebrow")}
          </p>
          <p className="font-display font-black text-white text-lg leading-tight line-clamp-2">{event.name}</p>
        </div>
      </div>

      <div className="p-4">
        {nFriends > 0 ? (
          <div className="flex items-center gap-2 mb-3">
            <div className="flex -space-x-2">
              {friends.slice(0, 5).map((f) => (
                <AvatarCircle key={f.user_id} name={f.name} picture={f.picture} size={28} ring />
              ))}
            </div>
            <span className="text-white/70 text-xs font-semibold">
              {t("nightrecap.coincided", { count: nFriends })}
            </span>
          </div>
        ) : (
          <p className="text-white/50 text-xs mb-3 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5" /> {t("nightrecap.no_friends")}
          </p>
        )}

        <div className="flex items-center gap-2">
          <button
            data-testid="recap-share-btn"
            onClick={() => shareOrDownload("share")}
            disabled={busy}
            className="flex-[2] py-3 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />} {t("nightrecap.share_night")}
          </button>
          <button
            data-testid="recap-download-btn"
            onClick={() => shareOrDownload("download")}
            disabled={busy}
            className="py-3 px-4 rounded-2xl bg-white/10 text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
            title={t("nightrecap.download")}
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
