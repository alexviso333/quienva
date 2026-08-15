import React, { useEffect, useRef, useState } from "react";
import { Ticket, ExternalLink, ShieldCheck, Loader2 } from "lucide-react";

/**
 * Compra de entradas integrada de forma NATIVA con el widget oficial de FourVenues.
 *
 * Objetivos (feedback del owner):
 *  - Que parezca de la propia app, no una "captura de FourVenues pegada":
 *      · theme=dark → el widget se pinta oscuro y combina con la app.
 *      · marco/tarjeta nativa (mismos bordes/colores que el resto de la ficha).
 *  - Que se AJUSTE a cada evento (sin scroll interno ni huecos): usamos el cargador
 *    OFICIAL de FourVenues, que auto-redimensiona el iframe a la altura real del
 *    contenido vía postMessage.
 *  - Que no "cargue más tarde y pegue un salto feo": mostramos un esqueleto nativo
 *    que reserva espacio hasta que el widget está listo.
 *  - Watchdog: si no carga, se muestra una tarjeta limpia + botón oficial (nunca un
 *    recuadro en blanco). El botón "Comprar en FourVenues ↗" está siempre disponible.
 */
export default function FourvenuesEmbed({ embedUrl, fallbackUrl, price, saleState, onBuyClick }) {
  const [status, setStatus] = useState("loading"); // loading | ok | failed
  const hostRef = useRef(null);

  useEffect(() => {
    if (!embedUrl || !hostRef.current) return undefined;
    const host = hostRef.current;
    setStatus("loading");
    // Contenedor que el cargador oficial rellena (evita su document.write).
    host.innerHTML = '<div id="fourvenues-iframe"></div>';

    // segments = "quienva/events/XXXX" -> cargador + tema oscuro para que combine.
    const segments = embedUrl.replace("https://www.fourvenues.com/iframe/", "");
    const loaderSrc = `https://www.fourvenues.com/assets/iframe/${segments}?theme=dark`;

    let settled = false;
    const onMsg = (e) => {
      try {
        if (typeof e.origin === "string" && e.origin.indexOf("fourvenues") !== -1) {
          if (!settled) {
            settled = true;
            setStatus("ok");
          }
        }
      } catch (_e) {
        /* ignore */
      }
    };
    window.addEventListener("message", onMsg);

    const script = document.createElement("script");
    script.src = loaderSrc;
    script.async = true;
    script.setAttribute("data-fv-embed", "1");
    document.body.appendChild(script);

    // Si en ~9s no ha dado senales de vida -> respaldo (nunca recuadro en blanco).
    const to = setTimeout(() => {
      if (!settled) setStatus("failed");
    }, 9000);

    return () => {
      window.removeEventListener("message", onMsg);
      clearTimeout(to);
      try {
        document.body.removeChild(script);
      } catch (_e) {
        /* already gone */
      }
      // Limpia lo que inyecta el cargador oficial para no dejar estado entre eventos.
      document.querySelectorAll("#fv_parent_script").forEach((n) => n.remove());
      document.querySelectorAll('script[src*="/assets/iframe/"]').forEach((n) => {
        if (n !== script) n.remove();
      });
      if (host) host.innerHTML = "";
    };
  }, [embedUrl]);

  const soldout = saleState === "agotado";

  const officialButton = (
    <a
      data-testid="detail-ticket-btn"
      href={fallbackUrl}
      target="_blank"
      rel="noopener noreferrer"
      onClick={onBuyClick}
      className={`min-h-[52px] rounded-2xl font-display font-black text-[15px] flex items-center justify-center gap-2 active:scale-95 transition-transform ${
        soldout
          ? "bg-white/10 text-white/70 border border-white/20"
          : "bg-gradient-to-r from-qv-primary to-qv-secondary text-black shadow-[0_0_24px_rgba(255,0,85,0.35)]"
      }`}
    >
      <Ticket className="w-5 h-5" />
      {soldout ? "Agotadas" : "Comprar en FourVenues"}
      <ExternalLink className="w-4 h-4 opacity-80" />
      {price && !soldout ? <span className="opacity-90"> desde {Math.round(price)}€</span> : null}
    </a>
  );

  return (
    <div className="flex flex-col gap-3">
      {/* Cabecera nativa */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Ticket className="w-4 h-4 text-qv-secondary" />
          <h3 className="font-display font-black text-white text-[15px]">Entradas</h3>
        </div>
        <span className="text-[11px] text-white/45 flex items-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5" /> Pago seguro
        </span>
      </div>

      {status !== "failed" ? (
        <div className="relative rounded-2xl overflow-hidden border border-white/10 bg-white/[0.03]">
          {/* Esqueleto mientras carga (reserva espacio, evita salto feo) */}
          {status === "loading" && (
            <div className="absolute inset-0 z-10 p-4 flex flex-col gap-3 qv-app-bg">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] p-4">
                  <div className="flex flex-col gap-2">
                    <div className="h-3.5 w-32 rounded bg-white/10 animate-pulse" />
                    <div className="h-3 w-20 rounded bg-white/5 animate-pulse" />
                  </div>
                  <div className="h-6 w-14 rounded-lg bg-white/10 animate-pulse" />
                </div>
              ))}
              <div className="mt-1 flex items-center justify-center gap-2 text-white/40 text-xs">
                <Loader2 className="w-4 h-4 animate-spin" /> Cargando entradas…
              </div>
            </div>
          )}
          {/* El cargador oficial rellena este host y auto-ajusta la altura */}
          <div ref={hostRef} className="w-full min-h-[220px]" />
        </div>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-center flex flex-col items-center gap-2">
          <ShieldCheck className="w-8 h-8 text-qv-secondary" />
          <p className="text-sm text-white/70 leading-snug">
            Compra tus entradas de forma <b className="text-white/90">segura</b> en FourVenues.
          </p>
        </div>
      )}

      {officialButton}

      <p className="text-center text-[11px] text-white/40 flex items-center justify-center gap-1">
        <ShieldCheck className="w-3 h-3" /> Precio oficial sin recargos
      </p>
    </div>
  );
}
