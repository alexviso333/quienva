import { useEffect, useState } from "react";

const KEY = "qv_compact_mode";
const EVENT = "qv-compact-changed";

export function getCompactMode() {
  try {
    // Compact is the DEFAULT now. Only "0" (explicit "vista completa") disables it.
    return localStorage.getItem(KEY) !== "0";
  } catch {
    return true;
  }
}

export function setCompactMode(v) {
  try {
    if (v) localStorage.removeItem(KEY); // default state = compact
    else localStorage.setItem(KEY, "0"); // user explicitly chose full view
    window.dispatchEvent(new Event(EVENT));
  } catch {
    /* ignore */
  }
}

/** React hook to reactively subscribe to compact-mode changes. */
export function useCompactMode() {
  const [compact, setCompact] = useState(getCompactMode);
  useEffect(() => {
    const handler = () => setCompact(getCompactMode());
    window.addEventListener(EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, []);
  return [compact, setCompactMode];
}
