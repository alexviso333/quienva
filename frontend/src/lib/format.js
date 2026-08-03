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

const _WD = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const _MO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const _pad = (n) => String(n).padStart(2, "0");

// The DATE (YYYY-MM-DD) a party belongs to. Backend already shifts 00:00 →
// 23:59 of the previous day, but keep a safeguard for any residual 00:00.
export function partyNightDate(dateStr, time) {
  const t = String(time || "").trim();
  if (t === "00:00" || t === "0:00" || t === "00:00:00") {
    try {
      const d = new Date(dateStr + "T00:00:00");
      d.setDate(d.getDate() - 1);
      return `${d.getFullYear()}-${_pad(d.getMonth() + 1)}-${_pad(d.getDate())}`;
    } catch {
      return dateStr;
    }
  }
  return dateStr;
}

// Human label like "vie 3 ago · 23:59". Shows the real start time, INCLUDING
// 23:59 (which now means "late night, from midnight" after the 00:00 shift).
// Only a missing/empty time is hidden.
export function formatPartyDate(dateStr, time) {
  const t = String(time || "").trim();
  const nd = partyNightDate(dateStr, t);
  let dateLabel = nd;
  try {
    const d = new Date(nd + "T00:00:00");
    dateLabel = `${_WD[d.getDay()]} ${d.getDate()} ${_MO[d.getMonth()]}`;
  } catch {
    /* keep raw */
  }
  const m = t.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return dateLabel; // no/empty time
  if (t === "00:00" || t === "0:00") return `${dateLabel} · 23:59`; // safeguard
  const hour = parseInt(m[1], 10);
  return `${dateLabel} · ${hour}:${m[2]}`;
}
