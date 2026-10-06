import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { isNativeApp } from "@/lib/platform";
import { attachNativePushTapHandler } from "@/lib/nativePush";

// Convierte cualquier enlace que abra la app en una ruta interna:
//   quienva://plan/<slug>        (toque en la isla dinámica / pantalla de bloqueo)
//   https://.../p/<slug>          (enlace compartido del plan)
//   /plan/<slug>, /event/<id>...  (url de una push)
export function toInternalPath(url) {
  if (!url || typeof url !== "string") return null;
  let path = url.trim();
  const custom = path.match(/^quienva:\/\/(.*)$/i);
  if (custom) {
    path = "/" + custom[1].replace(/^\/+/, "");
  } else if (/^https?:\/\//i.test(path)) {
    try {
      const u = new URL(path);
      path = u.pathname.replace(/^\/api(?=\/p\/)/, "") + u.search;
    } catch (e) {
      return null;
    }
  }
  if (!path.startsWith("/")) return null;
  // La página pública del plan (/p/slug) dentro de la app es siempre /plan/slug.
  path = path.replace(/^\/p\/(?!nuevo)([^/?#]+)/, "/plan/$1");
  if (path.startsWith("/auth-callback")) return null; // lo gestiona AuthContext
  return path;
}

// Solo app nativa: toques en push y en la Live Activity navegan DENTRO de la
// app (sin recargar ni abrir el navegador).
export default function NativeDeepLinks() {
  const navigate = useNavigate();
  useEffect(() => {
    if (!isNativeApp()) return undefined;
    let removeUrl = null;
    const go = (url) => {
      const path = toInternalPath(url);
      if (path) navigate(path);
    };
    attachNativePushTapHandler(go);
    (async () => {
      try {
        const { App: CapApp } = await import("@capacitor/app");
        const h = await CapApp.addListener("appUrlOpen", ({ url }) => {
          if (url && url.indexOf("auth-callback") === -1) go(url);
        });
        removeUrl = () => h.remove();
      } catch (e) { /* ignore */ }
    })();
    return () => { if (removeUrl) removeUrl(); };
  }, [navigate]);
  return null;
}
