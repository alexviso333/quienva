// Hide placeholder/filler times (e.g. scraped events that default to 23:59).
const PLACEHOLDER_TIMES = new Set(["23:59", "00:00", "0:00", "23:59:00", "00:00:00"]);

export function cleanTime(time) {
  if (!time) return "";
  const t = String(time).trim();
  if (PLACEHOLDER_TIMES.has(t)) return "";
  return t;
}

// " · 23:30" suffix helper (empty when placeholder/missing)
export function timeSuffix(time) {
  const t = cleanTime(time);
  return t ? ` · ${t}` : "";
}
