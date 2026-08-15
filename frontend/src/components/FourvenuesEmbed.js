import React from "react";
import { Ticket, ExternalLink, ShieldCheck } from "lucide-react";

/**
 * Sección de compra NATIVA para eventos que vendemos por FourVenues (slug quienva).
 *
 * Nota de diseño: NO usamos el iframe de FourVenues (quedaba como una "captura
 * pegada", cargaba tarde y no se ajustaba). En su lugar, tarjeta nativa con el
 * estilo de la app + botón oficial que abre el checkout de FourVenues (pago seguro
 * en su dominio, atribución a nuestro slug). El listado de entradas 100% nativo
 * (nombre/precio/estado por tipo) requiere la Channel Manager API de FourVenues.
 */
export default function FourvenuesEmbed({ fallbackUrl, price, saleState, onBuyClick }) {
  const soldout = saleState === "agotado";
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-9 h-9 rounded-xl bg-qv-secondary/15 flex items-center justify-center">
              <Ticket className="w-5 h-5 text-qv-secondary" />
            </span>
            <div className="leading-tight">
              <h3 className="font-display font-black text-white text-[15px]">Entradas</h3>
              <p className="text-[11px] text-white/45 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" /> Compra segura · precio oficial
              </p>
            </div>
          </div>
          {price && !soldout ? (
            <div className="text-right leading-tight">
              <p className="text-[10px] uppercase tracking-wider text-white/40">Desde</p>
              <p className="font-display font-black text-white text-lg">{Math.round(price)}€</p>
            </div>
          ) : null}
        </div>

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
          {soldout ? "Agotadas" : "Comprar entradas"}
          {!soldout ? <ExternalLink className="w-4 h-4 opacity-80" /> : null}
        </a>
      </div>
    </div>
  );
}
