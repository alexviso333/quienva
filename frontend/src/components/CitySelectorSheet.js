import { motion, AnimatePresence } from "framer-motion";
import { MapPin, X, Check } from "lucide-react";

// Semi-blocking city picker shown once on first app launch (and reopenable from
// the Feed header). Dismissible by design — the user can explore without choosing.
export default function CitySelectorSheet({
  open,
  cities = [],
  currentCity,
  onPick,
  onClose,
  dismissible = true,
  saving = false,
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[120] flex items-end justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          data-testid="city-selector-overlay"
        >
          {/* Backdrop */}
          <motion.div
            className="absolute inset-0 bg-black/75 backdrop-blur-md"
            onClick={dismissible ? onClose : undefined}
          />

          {/* Sheet */}
          <motion.div
            className="relative w-full max-w-md rounded-t-[28px] border-t border-white/10 overflow-hidden"
            style={{
              background:
                "linear-gradient(180deg,#15101e 0%,#0b0910 62%,#08070c 100%)",
              boxShadow: "0 -18px 60px -12px rgba(255,0,85,0.28)",
            }}
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 320 }}
            data-testid="city-selector-sheet"
          >
            {/* Neon top hairline */}
            <div className="h-[3px] w-full bg-gradient-to-r from-qv-primary via-qv-secondary to-qv-primary opacity-80" />

            <div className="px-6 pt-4 pb-8">
              {/* Grab handle */}
              <div className="mx-auto mb-5 h-1.5 w-10 rounded-full bg-white/15" />

              {/* Close */}
              {dismissible && (
                <button
                  onClick={onClose}
                  data-testid="city-selector-close"
                  aria-label="Cerrar"
                  className="absolute right-4 top-5 grid h-9 w-9 place-items-center rounded-full bg-white/8 text-white/60 active:scale-90 hover:text-white transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              )}

              {/* Header */}
              <div className="flex items-center gap-3">
                <span
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl border border-qv-secondary/30"
                  style={{ background: "rgba(0,240,255,0.12)" }}
                >
                  <MapPin className="h-5 w-5 text-qv-secondary" />
                </span>
                <div className="min-w-0">
                  <h2 className="font-display text-2xl font-black tracking-tight leading-none">
                    ¿Dónde sales<span className="text-qv-primary">?</span>
                  </h2>
                  <p className="mt-1 text-sm text-white/55">
                    Elige tu ciudad y verás sus fiestas.
                  </p>
                </div>
              </div>

              {/* Cities */}
              <div className="mt-6 grid grid-cols-2 gap-2.5">
                {cities.map((c, i) => {
                  const on = currentCity === c.id;
                  const label = (c.label || c.id).split(",")[0];
                  return (
                    <motion.button
                      key={c.id}
                      data-testid={`city-select-${c.id}`}
                      disabled={saving}
                      onClick={() => onPick(c.id)}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.04 * i + 0.05 }}
                      className={`relative flex items-center gap-2.5 rounded-2xl border px-3.5 py-3.5 text-left active:scale-[0.97] transition-colors disabled:opacity-60 ${
                        on
                          ? "border-qv-secondary bg-qv-secondary/10"
                          : "border-white/10 bg-white/[0.04] hover:border-white/25"
                      }`}
                      style={
                        on
                          ? { boxShadow: "0 0 20px -4px rgba(0,240,255,0.45)" }
                          : undefined
                      }
                    >
                      <span className="text-2xl leading-none">{c.emoji || "📍"}</span>
                      <span className="min-w-0 flex-1 truncate text-sm font-bold text-white">
                        {label}
                      </span>
                      {on && (
                        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-qv-secondary text-black">
                          <Check className="h-3 w-3" strokeWidth={3} />
                        </span>
                      )}
                    </motion.button>
                  );
                })}
              </div>

              {/* Dismiss */}
              {dismissible && (
                <button
                  onClick={onClose}
                  data-testid="city-selector-skip"
                  className="mt-5 w-full text-center text-sm font-semibold text-white/45 active:scale-95 hover:text-white/70 transition-colors"
                >
                  Explorar sin elegir
                </button>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
