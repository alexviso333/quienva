import { Lock } from "lucide-react";

// A few soft "head & shoulders" gradients so the cluster reads like real, but
// unrecognizable, blurred faces. No real user data is used — this is a pure
// growth hook for guests. Privacy-safe by construction.
const FACE_GRADIENTS = [
  "radial-gradient(circle at 50% 34%, #f0c9a0 0 30%, #c98b5e 62%, #2a1a10 100%)",
  "radial-gradient(circle at 50% 34%, #d9a887 0 30%, #a9714b 62%, #34210f 100%)",
  "radial-gradient(circle at 50% 34%, #cdb4d6 0 30%, #8a5f86 62%, #241826 100%)",
  "radial-gradient(circle at 50% 34%, #a8c3d6 0 30%, #5f7d8a 62%, #16222a 100%)",
  "radial-gradient(circle at 50% 34%, #e7b8b0 0 30%, #b56f66 62%, #2a1512 100%)",
];

function BlurredFace({ size, i }) {
  return (
    <div
      className="rounded-full overflow-hidden border-2 border-[#121215] shrink-0"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <div
        className="w-full h-full scale-125"
        style={{ background: FACE_GRADIENTS[i % FACE_GRADIENTS.length], filter: "blur(4px)" }}
      />
    </div>
  );
}

/**
 * Guest-only teaser: shows a cluster of blurred faces + the real going count
 * with a "regístrate para ver quién va" hook. `compact` renders a slim inline
 * variant for tiles (no own click handler — the parent tile navigates).
 */
export function BlurredGoingTeaser({ count, onClick, compact = false }) {
  const total = count || 0;
  if (total <= 0) return null;

  if (compact) {
    const n = Math.min(total, 3);
    return (
      <div className="flex items-center gap-1.5 mt-1.5" data-testid="guest-going-teaser-compact">
        <div className="flex -space-x-1.5">
          {Array.from({ length: n }).map((_, i) => (
            <BlurredFace key={i} i={i} size={18} />
          ))}
        </div>
        <span className="text-[10px] text-white/80 font-semibold truncate">
          {total} {total === 1 ? "va" : "van"} · <span className="text-qv-primary">ver quién</span>
        </span>
      </div>
    );
  }

  const n = Math.min(total, 4);
  const inner = (
    <>
      <div className="flex -space-x-2.5 shrink-0">
        {Array.from({ length: n }).map((_, i) => (
          <BlurredFace key={i} i={i} size={30} />
        ))}
      </div>
      <p className="text-xs leading-tight flex-1 min-w-0">
        <span className="font-semibold text-white">{total} {total === 1 ? "persona va" : "personas van"}</span>
        <span className="block text-qv-primary font-semibold">Regístrate para ver quién va</span>
      </p>
      <span className="shrink-0 w-7 h-7 rounded-full bg-qv-primary/15 border border-qv-primary/40 flex items-center justify-center">
        <Lock className="w-3.5 h-3.5 text-qv-primary" />
      </span>
    </>
  );

  // When no onClick is passed the teaser is embedded inside another button
  // (e.g. the event-detail guest block) → render a plain div to keep valid HTML.
  if (!onClick) {
    return (
      <div className="flex items-center gap-2.5 w-full text-left" data-testid="guest-going-teaser">
        {inner}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="guest-going-teaser"
      className="flex items-center gap-2.5 w-full text-left active:scale-[0.99] transition-transform"
    >
      {inner}
    </button>
  );
}
