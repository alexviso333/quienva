import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  // Cookies are NOT the primary auth (JWT in Authorization header is). Setting
  // withCredentials=false lets us work behind proxies that force
  // Access-Control-Allow-Origin: * (which browsers otherwise block).
  withCredentials: false,
});

// Bearer token is the primary auth mechanism.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("qv_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function mediaUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  return `${BACKEND_URL}${url}`;
}

// Insert a Cloudinary transformation right after "/upload/". Non-Cloudinary
// URLs (local /api/files) are returned untouched.
function cloudinaryTransform(url, transform) {
  if (!url || typeof url !== "string") return url;
  if (!url.includes("res.cloudinary.com") || !url.includes("/upload/")) return url;
  // Avoid double-inserting if a transform is already present.
  return url.replace(/\/upload\/(?!v\d|.*,)/, `/upload/${transform}/`).replace(
    /\/upload\/(v\d)/,
    `/upload/${transform}/$1`,
  );
}

// Optimized, auto-format, resized version for on-screen display (saves bandwidth,
// looks great, keeps the original untouched for downloads).
export function mediaThumb(url, width = 800) {
  const full = mediaUrl(url);
  return cloudinaryTransform(full, `f_auto,q_auto,w_${width},c_limit`);
}

// Force a full-quality download (original file) as an attachment.
export function mediaDownload(url) {
  const full = mediaUrl(url);
  return cloudinaryTransform(full, "fl_attachment");
}

// Robust cross-browser/mobile download. Opening a Cloudinary `fl_attachment`
// URL in a new tab often shows a blank page on iOS/Android instead of saving.
// Fetching the bytes and saving a Blob works everywhere (and falls back to a
// direct link if the fetch is blocked by CORS).
export async function downloadMedia(url, filename) {
  const src = mediaDownload(url);
  const name =
    filename ||
    (() => {
      try {
        const clean = (mediaUrl(url) || "").split("?")[0];
        const last = clean.substring(clean.lastIndexOf("/") + 1);
        return last || `quienva-${Date.now()}`;
      } catch {
        return `quienva-${Date.now()}`;
      }
    })();
  try {
    const res = await fetch(src, { mode: "cors" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 4000);
    return true;
  } catch (e) {
    // Fallback: open in a new tab so the user can save manually.
    try {
      window.open(src, "_blank", "noopener,noreferrer");
    } catch {
      /* ignore */
    }
    return false;
  }
}

// Native share of a media file (image/video). Fetches the bytes and uses the
// Web Share API with a File when supported (best on mobile: opens the OS share
// sheet with WhatsApp/Instagram/etc). Falls back to sharing the URL, and then
// to a plain download. Returns "shared" | "downloaded" | "cancelled".
export async function shareMedia(url, { title = "¿Quién va?", text = "", filename } = {}) {
  const displaySrc = mediaUrl(url);
  const dlSrc = mediaDownload(url);
  const name = filename || `quienva-${Date.now()}.jpg`;
  try {
    const res = await fetch(dlSrc, { mode: "cors" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const blob = await res.blob();
    const file = new File([blob], name, { type: blob.type || "image/jpeg" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({ files: [file], title, text });
      return "shared";
    }
    // No file-share support: try sharing the URL, else download the blob.
    if (navigator.share) {
      try {
        await navigator.share({ title, text, url: displaySrc });
        return "shared";
      } catch (_e) { /* fall through to download */ }
    }
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 4000);
    return "downloaded";
  } catch (e) {
    // Likely a user cancel (AbortError) or CORS/network issue.
    if (e && e.name === "AbortError") return "cancelled";
    try {
      if (navigator.share) { await navigator.share({ title, text, url: displaySrc }); return "shared"; }
      window.open(dlSrc, "_blank", "noopener,noreferrer");
    } catch { /* ignore */ }
    return "downloaded";
  }
}

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Algo salió mal. Inténtalo de nuevo.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default api;
