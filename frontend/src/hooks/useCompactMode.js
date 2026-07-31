import { useEffect, useState } from "react";

const KEY = "qv_compact_mode";
const EVENT = "qv-compact-changed";

export function getCompactMode() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setCompactMode(v) {
  try {
    if (v) localStorage.setItem(KEY, "1");
    else localStorage.removeItem(KEY);
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
