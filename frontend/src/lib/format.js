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

// The DATE (YYYY-MM-DD) of the night a party belongs to. A start time between
// 00:00 and 05:59 belongs to the PREVIOUS night (e.g. a party dated the 4th at
// 00:00 is really the night of the 3rd → 4th). Display-only; stored date is
// untouched. 23:59 is treated as the app's placeholder (not a real hour).
export function partyNightDate(dateStr, time) {
  const t = String(time || "").trim();
  const m = t.match(/^(\d{1,2}):(\d{2})/);
  const hour = m ? parseInt(m[1], 10) : null;
  if (t !== "23:59" && hour !== null && hour >= 0 && hour < 6) {
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

// Human label like "vie 3 ago · 00:30 · madrugada" using the night the party
// belongs to. Placeholder times (23:59) and missing times show just the date.
export function formatPartyDate(dateStr, time) {
  const nd = partyNightDate(dateStr, time);
  let dateLabel = nd;
  try {
    const d = new Date(nd + "T00:00:00");
    dateLabel = `${_WD[d.getDay()]} ${d.getDate()} ${_MO[d.getMonth()]}`;
  } catch {
    /* keep raw */
  }
  const t = String(time || "").trim();
  const m = t.match(/^(\d{1,2}):(\d{2})/);
  if (t === "23:59" || !m) return dateLabel; // placeholder / no time
  const hour = parseInt(m[1], 10);
  const hhmm = `${hour}:${m[2]}`;
  if (hour >= 0 && hour < 6) return `${dateLabel} · ${hhmm} · madrugada`;
  return `${dateLabel} · ${t.slice(0, 5)}`;
}
