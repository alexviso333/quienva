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
