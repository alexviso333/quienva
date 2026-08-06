import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { Zap, Camera, Loader2, X, RefreshCw, Timer, Users, ImageOff } from "lucide-react";
import { toast } from "sonner";

/**
 * Full-screen BeReal-style capture for "El Momento".
 * ONE tap captures BOTH cameras (rear first, then front) and composites them
 * into a single image (big rear photo + small front selfie overlay), then uploads.
 */
export default function Momento() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [camReady, setCamReady] = useState(false);
  const [camError, setCamError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [composed, setComposed] = useState(null); // { blob, url }
  const [uploading, setUploading] = useState(false);
  const [secLeft, setSecLeft] = useState(null);
  // Which camera fires FIRST (BeReal-style). Default: front ("user"). The other
  // camera is captured ~2.5s later, with a visible countdown so there's time to pose.
  const [firstCam, setFirstCam] = useState("user"); // "user" (frontal) | "environment" (trasera)
  const [poseMs, setPoseMs] = useState(3000);        // tiempo para posar entre las 2 cámaras
  const [countdown, setCountdown] = useState(null);  // big number shown between the two shots
  const fallbackRef = useRef(null);

  const { data: moment, isLoading } = useQuery({
    queryKey: ["active-moment"],
    queryFn: async () => (await api.get("/me/active-moment")).data,
    refetchInterval: 20000,
    retry: false,
  });

  const eventId = moment?.event_id;

  // ---- camera helpers ----
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const startCamera = useCallback(async (facing = "environment") => {
    setCamError(false);
    setCamReady(false);
    stopStream();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 1280 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setCamReady(true);
    } catch (e) {
      setCamError(true);
    }
  }, [stopStream]);

  useEffect(() => {
    if (composed) return; // don't reopen camera while previewing result
    if (moment?.active) startCamera(firstCam);
    return () => stopStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moment?.active, composed, firstCam]);

  // countdown for on-time bonus
  useEffect(() => {
    const dl = moment?.prompt?.on_time_deadline;
    if (!dl) { setSecLeft(null); return; }
    const tick = () => {
      const sec = Math.max(0, Math.round((new Date(dl).getTime() - Date.now()) / 1000));
      setSecLeft(sec);
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [moment?.prompt?.on_time_deadline]);

  const grabFrame = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return null;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    return c;
  };

  const waitFrames = (ms) => new Promise((r) => setTimeout(r, ms));

  // Visible countdown between the two shots so there's time to pose
  // (BeReal-style). One number per second: e.g. 3 → 2 → 1.
  const runCountdown = async (totalMs = 3000) => {
    const steps = Math.max(1, Math.round(totalMs / 1000));
    const each = Math.round(totalMs / steps);
    for (let i = steps; i >= 1; i--) {
      setCountdown(i);
      await waitFrames(each);
    }
    setCountdown(null);
  };

  // Draw a source canvas into dest as "cover" within target rect
  const drawCover = (ctx, src, dx, dy, dw, dh, mirror = false) => {
    const sr = src.width / src.height;
    const tr = dw / dh;
    let sw, sh, sx, sy;
    if (sr > tr) { sh = src.height; sw = sh * tr; sx = (src.width - sw) / 2; sy = 0; }
    else { sw = src.width; sh = sw / tr; sx = 0; sy = (src.height - sh) / 2; }
    ctx.save();
    if (mirror) { ctx.translate(dx + dw, dy); ctx.scale(-1, 1); ctx.drawImage(src, sx, sy, sw, sh, 0, 0, dw, dh); }
    else { ctx.drawImage(src, sx, sy, sw, sh, dx, dy, dw, dh); }
    ctx.restore();
  };

  const roundRect = (ctx, x, y, w, h, r) => {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  };

  const captureBoth = async () => {
    if (busy || !camReady) return;
    setBusy(true);
    try {
      // The camera currently showing is `firstCam`. Capture it NOW (user is ready),
      // then switch to the OTHER camera and give ~2.5s to pose before the 2nd shot.
      const secondCam = firstCam === "user" ? "environment" : "user";
      const shot1 = grabFrame();
      await startCamera(secondCam);
      // small buffer so the new camera stream is live before the countdown frames
      await waitFrames(400);
      await runCountdown(poseMs);
      const shot2 = grabFrame();
      stopStream();

      // Map the two shots to front/rear regardless of capture order so the
      // composition is always: big REAR photo + small FRONT selfie overlay.
      const front = firstCam === "user" ? shot1 : shot2;
      const rear = firstCam === "user" ? shot2 : shot1;

      // Compose portrait 900x1200
      const W = 900, H = 1200;
      const canvas = document.createElement("canvas");
      canvas.width = W; canvas.height = H;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, W, H);

      const main = rear || front;
      const mainIsFront = !rear;
      if (main) drawCover(ctx, main, 0, 0, W, H, mainIsFront);

      // overlay (front selfie, mirrored) top-left
      if (rear && front) {
        const ow = Math.round(W * 0.34);
        const oh = Math.round(ow * (H / W));
        const ox = 24, oy = 24;
        ctx.save();
        roundRect(ctx, ox, oy, ow, oh, 22);
        ctx.lineWidth = 6;
        ctx.strokeStyle = "rgba(0,0,0,0.55)";
        ctx.stroke();
        ctx.clip();
        drawCover(ctx, front, ox, oy, ow, oh, true);
        ctx.restore();
      }

      const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.88));
      if (!blob) throw new Error("No se pudo crear la imagen");
      setComposed({ blob, url: URL.createObjectURL(blob) });
    } catch (e) {
      toast.error("No se pudo capturar. Reintenta.");
      setCountdown(null);
      startCamera(firstCam);
    } finally {
      setBusy(false);
    }
  };

  const retake = () => {
    if (composed?.url) URL.revokeObjectURL(composed.url);
    setComposed(null);
  };

  const publish = async () => {
    if (!composed || !eventId) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", composed.blob, "momento.jpg");
      const { data } = await api.post(`/events/${eventId}/moment/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (data.on_time) toast.success("⭐ ¡A tiempo! +30 puntos");
      else toast.success("Momento subido ✨");
      qc.invalidateQueries({ queryKey: ["active-moment"] });
      qc.invalidateQueries({ queryKey: ["moment-status", eventId] });
      qc.invalidateQueries({ queryKey: ["moment-gallery", eventId] });
      qc.invalidateQueries({ queryKey: ["badges", "me"] });
      navigate(`/event/${eventId}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "No se pudo subir");
      setUploading(false);
    }
  };

  // Fallback file input (camera blocked) — single photo
  const onFallbackPick = async (e) => {
    const f = e.target.files?.[0];
    if (!f || !eventId) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", f);
      const { data } = await api.post(`/events/${eventId}/moment/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (data.on_time) toast.success("⭐ ¡A tiempo! +30 puntos");
      else toast.success("Momento subido ✨");
      qc.invalidateQueries({ queryKey: ["active-moment"] });
      navigate(`/event/${eventId}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "No se pudo subir");
      setUploading(false);
    }
  };

  // ---- render ----
  if (isLoading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="w-7 h-7 text-yellow-300 animate-spin" />
      </div>
    );
  }

  if (!moment?.active) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center px-8 text-center">
        <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-4">
          <Zap className="w-8 h-8 text-white/40" />
        </div>
        <h1 className="font-display text-2xl font-black text-white">No hay ningún Momento activo</h1>
        <p className="text-white/50 text-sm mt-2 max-w-xs">
          Cuando estés de fiesta te avisaremos con una notificación para hacer tu foto sorpresa. ¡Prepárate!
        </p>
        <button
          onClick={() => navigate("/feed")}
          className="mt-6 px-6 py-3 rounded-2xl bg-white/10 text-white font-bold text-sm active:scale-95"
          data-testid="momento-back"
        >
          Volver
        </button>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black z-[80] flex flex-col" data-testid="momento-page">
      {/* Top bar */}
      <div className="relative z-10 flex items-center justify-between px-4 pt-5 pb-3">
        <button
          onClick={() => navigate("/feed")}
          className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center active:scale-90"
          data-testid="momento-close"
        >
          <X className="w-5 h-5 text-white" />
        </button>
        <div className="text-center">
          <p className="font-display font-black text-white leading-none flex items-center gap-1.5 justify-center">
            <Zap className="w-4 h-4 text-yellow-300" /> El Momento
          </p>
          <p className="text-yellow-200/80 text-[11px] mt-0.5 truncate max-w-[200px]">{moment.event_name}</p>
        </div>
        <div className="w-10" />
      </div>

      {/* FOMO + countdown */}
      <div className="relative z-10 px-4 flex items-center justify-center gap-3 pb-2">
        {secLeft !== null && secLeft > 0 ? (
          <span className="flex items-center gap-1.5 text-yellow-300 font-display font-black text-lg tabular-nums">
            <Timer className="w-4 h-4" /> {Math.floor(secLeft / 60)}:{String(secLeft % 60).padStart(2, "0")}
            <span className="text-yellow-200/70 text-xs font-semibold ml-1">para +30 pts</span>
          </span>
        ) : (
          <span className="text-white/50 text-xs">Se acabó el bonus, pero aún cuenta ✨</span>
        )}
      </div>
      {moment.friends_captured > 0 && !composed && (
        <div className="relative z-10 px-4 flex items-center justify-center gap-1.5 pb-2">
          <Users className="w-3.5 h-3.5 text-qv-secondary" />
          <span className="text-white/70 text-xs font-semibold">
            {moment.friends_captured} amig{moment.friends_captured === 1 ? "o ya subió" : "os ya subieron"} el suyo · no te quedes fuera
          </span>
        </div>
      )}

      {/* Camera / preview area */}
      <div className="flex-1 relative flex items-center justify-center overflow-hidden">
        {composed ? (
          <img src={composed.url} alt="preview" className="w-full h-full object-contain" data-testid="momento-preview" />
        ) : camError ? (
          <div className="text-center px-8">
            <ImageOff className="w-10 h-10 text-white/40 mx-auto mb-3" />
            <p className="text-white/70 text-sm mb-4">No pudimos acceder a la cámara. Puedes subir una foto:</p>
            <button
              onClick={() => fallbackRef.current?.click()}
              className="px-6 py-3 rounded-2xl bg-yellow-300 text-black font-bold text-sm active:scale-95"
              data-testid="momento-fallback-btn"
            >
              <Camera className="w-4 h-4 inline mr-1" /> Subir foto
            </button>
            <input ref={fallbackRef} type="file" accept="image/*" capture="user" onChange={onFallbackPick} className="hidden" />
          </div>
        ) : (
          <>
            <video
              ref={videoRef}
              muted
              playsInline
              autoPlay
              className="w-full h-full object-cover"
              style={{ transform: firstCam === "user" && !busy ? "scaleX(-1)" : "none" }}
              data-testid="momento-video"
            />
            {!camReady && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                <Loader2 className="w-8 h-8 text-yellow-300 animate-spin" />
              </div>
            )}
            {busy && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60">
                {countdown !== null ? (
                  <>
                    <div
                      key={countdown}
                      className="w-28 h-28 rounded-full bg-yellow-300/95 flex items-center justify-center shadow-2xl animate-pulse"
                      data-testid="momento-countdown"
                    >
                      <span className="font-display font-black text-black text-6xl tabular-nums">{countdown}</span>
                    </div>
                    <p className="text-white font-bold text-sm mt-4">
                      ¡Posa! {firstCam === "user" ? "Ahora la cámara trasera" : "Ahora el selfie"}
                    </p>
                  </>
                ) : (
                  <>
                    <Loader2 className="w-8 h-8 text-yellow-300 animate-spin mb-2" />
                    <p className="text-white/80 text-sm font-semibold">Capturando las dos cámaras…</p>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Controls */}
      <div className="relative z-10 px-6 pb-8 pt-4">
        {composed ? (
          <div className="flex items-center gap-3">
            <button
              onClick={retake}
              disabled={uploading}
              className="flex-1 py-3.5 rounded-2xl bg-white/10 text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
              data-testid="momento-retake"
            >
              <RefreshCw className="w-4 h-4" /> Repetir
            </button>
            <button
              onClick={publish}
              disabled={uploading}
              className="flex-[2] py-3.5 rounded-2xl bg-yellow-300 text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
              data-testid="momento-publish"
            >
              {uploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Subiendo…</> : <>Publicar mi Momento</>}
            </button>
          </div>
        ) : !camError ? (
          <div className="flex flex-col items-center">
            {/* Choose which camera fires FIRST */}
            <div className="flex items-center gap-1 p-1 rounded-full bg-white/10 mb-4" data-testid="momento-cam-toggle">
              <button
                onClick={() => !busy && setFirstCam("user")}
                disabled={busy}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition ${firstCam === "user" ? "bg-yellow-300 text-black" : "text-white/70"}`}
                data-testid="momento-cam-front"
              >
                Frontal primero
              </button>
              <button
                onClick={() => !busy && setFirstCam("environment")}
                disabled={busy}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition ${firstCam === "environment" ? "bg-yellow-300 text-black" : "text-white/70"}`}
                data-testid="momento-cam-back"
              >
                Trasera primero
              </button>
            </div>
            {/* Tiempo para posar entre las dos cámaras */}
            <div className="flex items-center gap-1 p-1 rounded-full bg-white/10 mb-4" data-testid="momento-pose-toggle">
              <span className="text-white/50 text-[11px] font-semibold pl-2 pr-1">Pose</span>
              {[2, 3, 4].map((s) => (
                <button
                  key={s}
                  onClick={() => !busy && setPoseMs(s * 1000)}
                  disabled={busy}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold transition ${poseMs === s * 1000 ? "bg-yellow-300 text-black" : "text-white/70"}`}
                  data-testid={`momento-pose-${s}`}
                >
                  {s}s
                </button>
              ))}
            </div>
            <button
              onClick={captureBoth}
              disabled={!camReady || busy}
              className="w-20 h-20 rounded-full bg-white flex items-center justify-center active:scale-90 disabled:opacity-50 ring-4 ring-white/30"
              data-testid="momento-shutter"
            >
              <div className="w-16 h-16 rounded-full bg-yellow-300 flex items-center justify-center">
                <Camera className="w-7 h-7 text-black" />
              </div>
            </button>
            <p className="text-white/50 text-xs mt-3">Un toque: primero la {firstCam === "user" ? "frontal" : "trasera"} y, tras {poseMs / 1000} s para posar, la otra</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
