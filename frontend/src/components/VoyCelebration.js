import { useEffect, useState } from "react";

// Pequeña celebración de una sola vez al marcar "VOY": un anillo neón que
// estalla + unas chispas de confeti. Sobrio y rápido (~0.8s), no intrusivo.
// Se remonta vía `key` desde el padre para re-disparar la animación.
const PIECES = Array.from({ length: 12 }).map((_, i) => {
  const angle = (Math.PI * 2 * i) / 12 + (i % 2 ? 0.3 : 0);
  const dist = 40 + (i % 3) * 14;
  return {
    cx: Math.cos(angle) * dist,
    cy: Math.sin(angle) * dist - 8,
    cr: (i % 2 ? 1 : -1) * (120 + i * 16),
    color: i % 3 === 0 ? "#FF0055" : i % 3 === 1 ? "#00F0FF" : "#FFD400",
    delay: (i % 4) * 25,
  };
});

export function VoyCelebration() {
  const [done, setDone] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setDone(true), 850);
    return () => clearTimeout(id);
  }, []);
  if (done) return null;
  return (
    <span className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center overflow-visible">
      <span className="qv-ring-burst" />
      {PIECES.map((p, i) => (
        <span
          key={i}
          className="qv-confetti-piece"
          style={{
            background: p.color,
            "--qv-cx": `${p.cx}px`,
            "--qv-cy": `${p.cy}px`,
            "--qv-cr": `${p.cr}deg`,
            animationDelay: `${p.delay}ms`,
          }}
        />
      ))}
    </span>
  );
}
