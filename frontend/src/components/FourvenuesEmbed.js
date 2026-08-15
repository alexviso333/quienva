import React, { useEffect, useRef, useState } from "react";
import { Ticket, ExternalLink, ShieldCheck, Loader2 } from "lucide-react";

/**
 * Compra embebida con el widget OFICIAL de FourVenues.
 *
 * - Incrusta https://www.fourvenues.com/iframe/<rrpp>/events/<code> (nuestro slug
 *   va en la URL → la venta se nos atribuye sin depender de cookies de terceros).
 * - "Watchdog": si el iframe no emite ningún mensaje de fourvenues en unos segundos
 *   (bloqueado / no carga), lo sustituimos por una tarjeta limpia con el botón
 *   oficial → NUNCA se queda un recuadro en blanco.
 * - El botón "Comprar en FourVenues ↗" está SIEMPRE visible: es el respaldo para
 *   quien no se fíe del recuadro y garantiza la compra (pago en el dominio oficial).
 */
export default function FourvenuesEmbed({ embedUrl, fallbackUrl, price, saleState, onBuyClick }) {
  const [status, setStatus] = useState("loading"); // loading | ok | failed
  const timerRef = useRef(null);

  useEffect(() => {
    if (!embedUrl) return undefined;
    setStatus("loading");
    let settled = false;

    const onMsg = (e) => {
      try {
        if (typeof e.origin === "string" && e.origin.indexOf("fourvenues") !== -1) {
          settled = true;
          setStatus("ok");
        }
      } catch (_e) {
        /* ignore */
      }
    };
    window.addEventListener("message", onMsg);
    timerRef.current = setTimeout(() => {
      if (!settled) setStatus("failed");
    }, 8000);

    return () => {
      window.removeEventListener("message", onMsg);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [embedUrl]);

  const soldout = saleState === "agotado";

  const OfficialButton = (
    <a
      data-testid="detail-ticket-btn"
      href={fallbackUrl}
      target="_blank"
      rel="noopener noreferrer"
      onClick={onBuyClick}
      className={`h-14 rounded-2xl font-display font-black text-base flex items-center justify-center gap-2 active:scale-95 transition-transform ${
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
    <div className="flex flex-col gap-2">
      {status !== "failed" ? (
        <div className="relative rounded-2xl overflow-hidden border border-white/15 bg-white/[0.03]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10 bg-white/[0.02]">
            <ShieldCheck className="w-4 h-4 text-qv-secondary" />
            <span className="text-xs font-semibold text-white/70">Compra segura · FourVenues</span>
          </div>
          {status === "loading" && (
            <div className="absolute inset-x-0 top-10 h-[560px] flex flex-col items-center justify-center gap-2 text-white/50 text-sm pointer-events-none">
              <Loader2 className="w-6 h-6 animate-spin" />
              Cargando compra segura…
            </div>
          )}
          <iframe
            title="Comprar entradas en FourVenues"
            src={embedUrl}
            className="w-full block"
            style={{ height: 620, border: 0, background: "transparent" }}
            allow="payment"
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
          />
        </div>
      ) : (
        <div className="rounded-2xl border border-white/15 bg-white/[0.03] p-5 text-center flex flex-col items-center gap-3">
          <ShieldCheck className="w-9 h-9 text-qv-secondary" />
          <p className="text-sm text-white/70 leading-snug">
            Compra tus entradas de forma <b className="text-white/90">100% segura</b> en la web oficial de FourVenues.
          </p>
        </div>
      )}

      {/* Botón oficial: SIEMPRE visible (respaldo + garantía de compra) */}
      {OfficialButton}

      <p className="text-center text-[11px] text-white/40 flex items-center justify-center gap-1">
        <ShieldCheck className="w-3 h-3" /> Pago 100% seguro en la web oficial · Precio oficial sin recargos
      </p>
    </div>
  );
}
