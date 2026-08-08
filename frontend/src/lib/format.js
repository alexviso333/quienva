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

import i18n from "@/i18n";

const _WD_BY_LANG = {
  es: ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"],
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  de: ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
};
const _MO_BY_LANG = {
  es: ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  de: ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
};
const _lang = () => (i18n.language || "es").slice(0, 2);
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
  const lang = _lang();
  const WD = _WD_BY_LANG[lang] || _WD_BY_LANG.es;
  const MO = _MO_BY_LANG[lang] || _MO_BY_LANG.es;
  try {
    const d = new Date(nd + "T00:00:00");
    dateLabel = `${WD[d.getDay()]} ${d.getDate()} ${MO[d.getMonth()]}`;
  } catch {
    /* keep raw */
  }
  const m = t.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return dateLabel; // no/empty time
  if (t === "00:00" || t === "0:00") return `${dateLabel} · 23:59`; // safeguard
  const hour = parseInt(m[1], 10);
  return `${dateLabel} · ${hour}:${m[2]}`;
}

// Haversine distance in km between two [lat, lng] points.
export function haversineKm(a, b) {
  if (!a || !b) return Infinity;
  const R = 6371;
  const dLat = ((b[0] - a[0]) * Math.PI) / 180;
  const dLng = ((b[1] - a[1]) * Math.PI) / 180;
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

// Human label for a distance in km: "350 m" / "2,4 km".
export function formatKm(km) {
  if (km == null || !Number.isFinite(km)) return "";
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1).replace(".", ",")} km`;
}
