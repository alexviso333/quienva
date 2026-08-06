import { useMemo, useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { mediaThumb } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import {
  X, ChevronLeft, ChevronRight, Share2, Download, Loader2,
  Sparkles, PartyPopper, Building2, Music2, Camera, Users, CalendarDays, Images, Zap,
} from "lucide-react";
import { toast } from "sonner";

function prevMonth(mstr) {
  const y = parseInt(mstr.slice(0, 4), 10);
  const m = parseInt(mstr.slice(5, 7), 10);
  const d = new Date(y, m - 1, 1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function nextMonth(mstr) {
  const y = parseInt(mstr.slice(0, 4), 10);
  const m = parseInt(mstr.slice(5, 7), 10);
  const d = new Date(y, m - 1, 1);
  d.setMonth(d.getMonth() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function thisYear() {
  return String(new Date().getFullYear());
}

const GRADS = [
  "from-[#2a0a3d] via-[#12071f] to-black",
  "from-[#3d0a24] via-[#1a0710] to-black",
  "from-[#0a2a3d] via-[#07141f] to-black",
  "from-[#3d2a0a] via-[#1f1407] to-black",
  "from-[#0a3d2a] via-[#071f14] to-black",
  "from-[#1a0a3d] via-[#0e071f] to-black",
];

export default function Wrapped() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const isYear = params.has("year");
  const month = params.get("month") || prevMonth(thisMonth());
  const year = params.get("year") || thisYear();
  const period = isYear ? year : month;
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const touchX = useRef(null);

  const { data, isLoading } = useQuery({
    queryKey: ["wrapped", isYear ? "y" : "m", period],
    queryFn: async () => (
      await api.get(isYear ? `/me/wrapped/year?year=${year}` : `/me/wrapped?month=${month}`)
    ).data,
  });

  const slides = useMemo(() => {
    if (!data || !data.has_data) return [];
    const s = [];
    s.push({ key: "intro" });
    s.push({ key: "parties" });
    if (data.is_year && data.top_month) s.push({ key: "topmonth" });
    if (data.top_venue) s.push({ key: "venue" });
    if (data.top_genre) s.push({ key: "genre" });
    if ((data.photos || 0) + (data.moments || 0) > 0) s.push({ key: "media" });
    if ((data.gallery || []).length > 0) s.push({ key: "gallery" });
    if ((data.friends_coincided || 0) > 0) s.push({ key: "friends" });
    s.push({ key: "final" });
    return s;
  }, [data]);

  useEffect(() => { setIdx(0); }, [period, isYear]);

  const go = (dir) => {
    setIdx((i) => Math.min(Math.max(i + dir, 0), Math.max(slides.length - 1, 0)));
  };

  const changePeriod = (dir) => {
    if (isYear) {
      setParams({ year: String(parseInt(year, 10) + dir) });
    } else {
      setParams({ month: dir < 0 ? prevMonth(month) : nextMonth(month) });
    }
  };

  const isCurrent = isYear ? (year === thisYear()) : (month === prevMonth(thisMonth()));

  // ---- Shareable image ----
  const buildImage = async () => {
    const W = 1080, H = 1920;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const ctx = c.getContext("2d");
    const grd = ctx.createLinearGradient(0, 0, W, H);
    grd.addColorStop(0, "#2a0a3d"); grd.addColorStop(0.5, "#12071f"); grd.addColorStop(1, "#000000");
    ctx.fillStyle = grd; ctx.fillRect(0, 0, W, H);
    // decorative poster (blurred-ish via low alpha) top corner
    if (data.poster) {
      try {
        const res = await fetch(mediaThumb(data.poster, 720), { mode: "cors" });
        const bmp = await createImageBitmap(await res.blob());
        ctx.globalAlpha = 0.28;
        ctx.drawImage(bmp, 0, 0, W, Math.round(H * 0.42));
        ctx.globalAlpha = 1;
        const g2 = ctx.createLinearGradient(0, 0, 0, H * 0.42);
        g2.addColorStop(0, "rgba(0,0,0,0.2)"); g2.addColorStop(1, "#12071f");
        ctx.fillStyle = g2; ctx.fillRect(0, 0, W, Math.round(H * 0.42));
      } catch (_e) { /* ignore */ }
    }
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#FFD400";
    ctx.font = "800 46px system-ui, sans-serif";
    ctx.fillText(data.is_year ? "MI WRAPPED ANUAL" : "MI WRAPPED", 80, 200);
    ctx.fillStyle = "#ffffff";
    ctx.font = "900 92px system-ui, sans-serif";
    ctx.fillText(data.month_label, 80, 300);

    const rows = [
      [`${data.parties}`, `fiesta${data.parties === 1 ? "" : "s"}`],
      [`${data.nights_out}`, "noches fuera"],
      (data.is_year && data.top_month) ? [data.top_month.name, "tu mes más movido"] : null,
      data.top_venue ? [data.top_venue.name, "tu sala top"] : null,
      data.top_genre ? [data.top_genre, "tu género top"] : null,
      [`${data.photos}`, "fotos"],
      [`${data.moments}`, `momentos${data.moments_ontime ? ` (${data.moments_ontime} a tiempo)` : ""}`],
      (data.friends_coincided ? [`${data.friends_coincided}`, "amig@s con los que coincidiste"] : null),
    ].filter(Boolean);

    let y = 470;
    for (const [big, small] of rows) {
      ctx.fillStyle = "#FF2E7E";
      ctx.font = "900 78px system-ui, sans-serif";
      const bigStr = String(big).length > 16 ? String(big).slice(0, 15) + "…" : String(big);
      ctx.fillText(bigStr, 80, y);
      ctx.fillStyle = "rgba(255,255,255,0.72)";
      ctx.font = "500 40px system-ui, sans-serif";
      ctx.fillText(small, 80, y + 52);
      y += 175;
    }
    // Title badge
    ctx.fillStyle = "#FFD400";
    ctx.font = "800 52px system-ui, sans-serif";
    ctx.fillText(data.title || "", 80, y + 10);
    // Watermark
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.font = "900 48px system-ui, sans-serif";
    ctx.fillText("¿Quién va?", 80, H - 70);
    return await new Promise((res) => c.toBlob(res, "image/jpeg", 0.92));
  };

  const shareOrDownload = async (mode) => {
    if (busy || !data) return;
    setBusy(true);
    try {
      const blob = await buildImage();
      const file = new File([blob], `wrapped-${period}.jpg`, { type: "image/jpeg" });
      if (mode === "share" && navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: "Mi Wrapped", text: `Mi ${data.month_label} en ¿Quién va? ✨` });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `wrapped-${period}.jpg`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        if (mode === "share") toast.success("Imagen guardada — compártela donde quieras ✨");
      }
    } catch (e) {
      if (!(e && e.name === "AbortError")) toast.error("No se pudo generar la imagen");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black text-white select-none overflow-hidden"
      onTouchStart={(e) => { touchX.current = e.touches[0].clientX; }}
      onTouchEnd={(e) => {
        if (touchX.current == null) return;
        const dx = e.changedTouches[0].clientX - touchX.current;
        if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
        touchX.current = null;
      }}
    >
      {/* Progress bars */}
      {slides.length > 0 && (
        <div className="absolute top-0 left-0 right-0 z-30 flex gap-1 p-3 pt-4">
          {slides.map((_, i) => (
            <div key={i} className="flex-1 h-1 rounded-full bg-white/25 overflow-hidden">
              <div className={`h-full bg-white transition-all duration-300 ${i <= idx ? "w-full" : "w-0"}`} />
            </div>
          ))}
        </div>
      )}

      {/* Header controls */}
      <div className="absolute top-4 right-3 z-30 flex items-center gap-2 pt-3">
        <button onClick={() => nav("/profile")} className="w-9 h-9 rounded-full bg-black/40 flex items-center justify-center" data-testid="wrapped-close">
          <X className="w-5 h-5" />
        </button>
      </div>
      <div className="absolute top-4 left-3 z-30 flex items-center gap-1 pt-3">
        <button onClick={() => changePeriod(-1)} className="w-9 h-9 rounded-full bg-black/40 flex items-center justify-center" data-testid="wrapped-prev-period" title={isYear ? "Año anterior" : "Mes anterior"}>
          <ChevronLeft className="w-5 h-5" />
        </button>
        {!isCurrent && (
          <button onClick={() => changePeriod(1)} className="w-9 h-9 rounded-full bg-black/40 flex items-center justify-center" data-testid="wrapped-next-period" title={isYear ? "Año siguiente" : "Mes siguiente"}>
            <ChevronRight className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Month / Year toggle */}
      {slides.length >= 0 && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 p-1 rounded-full bg-black/45 backdrop-blur">
          <button
            onClick={() => setParams({ month: prevMonth(thisMonth()) })}
            className={`px-3 py-1 rounded-full text-xs font-bold ${!isYear ? "bg-white text-black" : "text-white/70"}`}
            data-testid="wrapped-mode-month"
          >
            Mes
          </button>
          <button
            onClick={() => setParams({ year: thisYear() })}
            className={`px-3 py-1 rounded-full text-xs font-bold ${isYear ? "bg-white text-black" : "text-white/70"}`}
            data-testid="wrapped-mode-year"
          >
            Año
          </button>
        </div>
      )}

      {/* Tap zones */}
      {slides.length > 0 && (
        <>
          <button className="absolute left-0 top-0 bottom-0 w-1/3 z-20" onClick={() => go(-1)} aria-label="anterior" data-testid="wrapped-tap-prev" />
          <button className="absolute right-0 top-0 bottom-0 w-1/3 z-20" onClick={() => go(1)} aria-label="siguiente" data-testid="wrapped-tap-next" />
        </>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="h-full flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-white/60" /></div>
      ) : !data || !data.has_data ? (
        <div className={`h-full flex flex-col items-center justify-center text-center px-8 bg-gradient-to-b ${GRADS[0]}`}>
          <Sparkles className="w-12 h-12 text-yellow-300 mb-4" />
          <h2 className="font-display text-2xl font-black mb-2">Tu Wrapped {isYear ? "de" : "de"} {data?.month_label || ""}</h2>
          <p className="text-white/60 text-sm max-w-xs">Todavía no hay actividad {isYear ? "este año" : "este mes"}. ¡Marca fiestas, sube fotos y captura El Momento para llenar tu resumen! 🎉</p>
          <button onClick={() => changePeriod(-1)} className="mt-6 px-5 py-2.5 rounded-full bg-white/10 font-bold text-sm flex items-center gap-2">
            <ChevronLeft className="w-4 h-4" /> Ver el {isYear ? "año" : "mes"} anterior
          </button>
          <button onClick={() => nav("/profile")} className="mt-3 text-white/50 text-sm">Volver</button>
        </div>
      ) : (
        <div className={`h-full w-full flex flex-col items-center justify-center text-center px-8 bg-gradient-to-br ${GRADS[idx % GRADS.length]} transition-colors duration-500`}>
          <SlideContent slide={slides[idx]} data={data} onShare={() => shareOrDownload("share")} onDownload={() => shareOrDownload("download")} busy={busy} />
        </div>
      )}
    </div>
  );
}

function Stat({ big, children }) {
  return (
    <div className="mb-2">
      <div className="font-display font-black text-yellow-300 leading-none" style={{ fontSize: "5.5rem" }}>{big}</div>
      <div className="text-white/70 text-base mt-2">{children}</div>
    </div>
  );
}

function SlideContent({ slide, data, onShare, onDownload, busy }) {
  const k = slide.key;
  if (k === "intro") {
    return (
      <div className="animate-fade-in">
        <Sparkles className="w-14 h-14 text-yellow-300 mx-auto mb-5" />
        <p className="text-yellow-300 font-black uppercase tracking-widest text-sm">{data.is_year ? "Mi Wrapped Anual" : "Mi Wrapped"}</p>
        <h1 className="font-display font-black text-5xl leading-none mt-2">{data.month_label}</h1>
        <p className="text-white/60 mt-5 max-w-xs mx-auto">Tu {data.is_year ? "año" : "mes"} de fiesta en ¿Quién va? Desliza para verlo 👉</p>
      </div>
    );
  }
  if (k === "parties") {
    return (
      <div className="animate-fade-in">
        <PartyPopper className="w-12 h-12 text-white/80 mx-auto mb-6" />
        <Stat big={data.parties}>fiesta{data.parties === 1 ? "" : "s"} {data.is_year ? "este año" : "este mes"}</Stat>
        <p className="text-white/60 mt-4">{data.nights_out} noche{data.nights_out === 1 ? "" : "s"} fuera · {data.venues} sala{data.venues === 1 ? "" : "s"} distintas</p>
      </div>
    );
  }
  if (k === "topmonth") {
    return (
      <div className="animate-fade-in">
        <CalendarDays className="w-12 h-12 text-white/80 mx-auto mb-6" />
        <p className="text-white/60 uppercase tracking-widest text-xs font-bold mb-3">Tu mes más movido</p>
        <h2 className="font-display font-black text-5xl leading-tight">{data.top_month.name}</h2>
        <p className="text-white/60 mt-4">{data.top_month.count} fiesta{data.top_month.count === 1 ? "" : "s"} solo ese mes 🔥</p>
      </div>
    );
  }
  if (k === "venue") {
    return (
      <div className="animate-fade-in">
        <Building2 className="w-12 h-12 text-white/80 mx-auto mb-6" />
        <p className="text-white/60 uppercase tracking-widest text-xs font-bold mb-3">Tu sala top</p>
        <h2 className="font-display font-black text-4xl leading-tight">{data.top_venue.name}</h2>
        <p className="text-white/60 mt-4">Fuiste {data.top_venue.count} {data.top_venue.count === 1 ? "vez" : "veces"} 🔥</p>
      </div>
    );
  }
  if (k === "genre") {
    return (
      <div className="animate-fade-in">
        <Music2 className="w-12 h-12 text-white/80 mx-auto mb-6" />
        <p className="text-white/60 uppercase tracking-widest text-xs font-bold mb-3">Tu género top</p>
        <h2 className="font-display font-black text-5xl leading-tight capitalize">{data.top_genre}</h2>
        <p className="text-yellow-300 font-black text-xl mt-5">{data.title}</p>
      </div>
    );
  }
  if (k === "media") {
    return (
      <div className="animate-fade-in">
        <Camera className="w-12 h-12 text-white/80 mx-auto mb-6" />
        <div className="flex items-center justify-center gap-8">
          <div><div className="font-display font-black text-yellow-300 text-6xl leading-none">{data.photos}</div><div className="text-white/70 mt-2">fotos</div></div>
          <div><div className="font-display font-black text-qv-secondary text-6xl leading-none">{data.moments}</div><div className="text-white/70 mt-2">momentos</div></div>
        </div>
        {data.moments_ontime > 0 && <p className="text-white/60 mt-6">{data.moments_ontime} momento{data.moments_ontime === 1 ? "" : "s"} capturado{data.moments_ontime === 1 ? "" : "s"} a tiempo ⚡</p>}
      </div>
    );
  }
  if (k === "gallery") {
    const g = (data.gallery || []).slice(0, 9);
    return (
      <div className="animate-fade-in w-full max-w-sm">
        <Images className="w-12 h-12 text-white/80 mx-auto mb-4" />
        <p className="text-white/60 uppercase tracking-widest text-xs font-bold mb-4">Tus fotos y momentos</p>
        <div className="grid grid-cols-3 gap-1.5">
          {g.map((it, i) => (
            <div key={i} className="aspect-square rounded-xl overflow-hidden bg-white/5 relative">
              <img src={mediaThumb(it.url, 400)} alt="" className="w-full h-full object-cover" loading="lazy" />
              {it.kind === "moment" && (
                <div className="absolute top-1 left-1 w-5 h-5 rounded-full bg-yellow-300 flex items-center justify-center">
                  <Zap className="w-3 h-3 text-black" />
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="text-white/45 text-xs mt-4">{data.photos} foto{data.photos === 1 ? "" : "s"} · {data.moments} momento{data.moments === 1 ? "" : "s"} este {data.is_year ? "año" : "mes"}</p>
      </div>
    );
  }
  if (k === "friends") {
    return (
      <div className="animate-fade-in">
        <Users className="w-12 h-12 text-white/80 mx-auto mb-6" />
        <Stat big={data.friends_coincided}>amig@s con los que coincidiste</Stat>
        {data.top_friends?.length > 0 && (
          <div className="mt-6 flex flex-col items-center gap-3">
            {data.top_friends.map((f, i) => (
              <div key={i} className="flex items-center gap-3 bg-white/5 rounded-full pr-5 pl-1.5 py-1.5">
                <AvatarCircle name={f.name} picture={f.picture} size={36} ring />
                <span className="font-bold">{f.name}</span>
                <span className="text-white/50 text-sm">· {f.count} noche{f.count === 1 ? "" : "s"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  // final
  return (
    <div className="animate-fade-in w-full max-w-sm">
      <p className="text-yellow-300 font-black uppercase tracking-widest text-xs">Mi Wrapped · {data.month_label}</p>
      <h2 className="font-display font-black text-3xl mt-2 mb-5">{data.title}</h2>
      <div className="grid grid-cols-2 gap-3 text-left">
        <MiniStat n={data.parties} label="fiestas" />
        <MiniStat n={data.nights_out} label="noches fuera" />
        <MiniStat n={data.photos} label="fotos" />
        <MiniStat n={data.moments} label="momentos" />
        {data.top_venue && <MiniStat n={data.top_venue.name} label="sala top" small />}
        {data.top_genre && <MiniStat n={data.top_genre} label="género top" small />}
      </div>
      <div className="flex items-center gap-2 mt-7">
        <button data-testid="wrapped-share" onClick={onShare} disabled={busy} className="flex-[2] py-3.5 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60">
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Share2 className="w-5 h-5" />} Compartir
        </button>
        <button data-testid="wrapped-download" onClick={onDownload} disabled={busy} className="py-3.5 px-5 rounded-2xl bg-white/10 font-bold active:scale-95 disabled:opacity-60">
          <Download className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}

function MiniStat({ n, label, small }) {
  return (
    <div className="rounded-2xl bg-white/[0.06] border border-white/10 p-3">
      <div className={`font-display font-black text-yellow-300 leading-tight ${small ? "text-lg truncate capitalize" : "text-3xl"}`}>{n}</div>
      <div className="text-white/60 text-xs mt-0.5">{label}</div>
    </div>
  );
}
