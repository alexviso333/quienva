import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "@/lib/notify";
import { refreshNativePushIfGranted } from "@/lib/nativePush";
import { registerMomentStartToken } from "@/lib/momentLiveActivity";
import { registerPlanStartToken } from "@/lib/liveActivity";
import { isNativeApp } from "@/lib/platform";
import { captureEvent, identifyUser, resetAnalytics } from "@/analytics/posthog";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On the native app, whenever we have a logged-in user, silently re-register
  // the APNs device token so the backend always has a fresh, valid token.
  // Also subscribe the Live Activity push-to-start tokens (Momento +
  // invitación a plan) so the backend can launch the Dynamic Island remotely.
  useEffect(() => {
    if (user?.user_id) {
      refreshNativePushIfGranted();
      registerMomentStartToken();
      registerPlanStartToken();
    }
  }, [user?.user_id]);

  const checkAuth = useCallback(async () => {
    // Optimistic hydrate from the last-known user so the app opens INSTANTLY
    // (even with poor/no coverage) instead of flashing the login screen.
    let hadCached = false;
    try {
      const cached = localStorage.getItem("qv_user");
      const token = localStorage.getItem("qv_token");
      if (cached && token) {
        setUser(JSON.parse(cached));
        hadCached = true;
      }
    } catch (e) { /* ignore */ }
    try {
      // Per-request timeout so a hung /auth/me (cold backend or a WebView that
      // silently drops the request) can never freeze the app on launch — the
      // check resolves and the UI proceeds instead of an infinite spinner.
      const { data } = await api.get("/auth/me", { timeout: 15000 });
      setUser(data);
      try { localStorage.setItem("qv_user", JSON.stringify(data)); } catch (e) { /* ignore */ }
    } catch (e) {
      const status = e?.response?.status;
      if (status === 401 || status === 403) {
        // Real auth failure → log out and clear the cached session.
        setUser(null);
        try { localStorage.removeItem("qv_user"); } catch (er) { /* ignore */ }
      } else if (!hadCached) {
        // Network error and nothing cached → treat as logged out.
        setUser(null);
      }
      // Network error WITH a cached session → keep it (offline-friendly).
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Skip /me check while returning from Google OAuth callback
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  // NATIVE app only: Google login happens in the system browser (Safari) and the
  // web callback bounces the session back here via the custom URL scheme
  // (quienva://auth-callback?token=...). Catch it, store the session, load user.
  useEffect(() => {
    if (!isNativeApp()) return;
    let remove;
    (async () => {
      try {
        const { App: CapApp } = await import("@capacitor/app");
        const handle = await CapApp.addListener("appUrlOpen", async ({ url }) => {
          try {
            if (!url || url.indexOf("auth-callback") === -1) return;
            let token = null;
            let isNew = false;
            try {
              const u = new URL(url);
              token = u.searchParams.get("token");
              isNew = u.searchParams.get("is_new") === "1";
            } catch (e) { /* ignore */ }
            if (!token) {
              const m = url.match(/[?&]token=([^&]+)/);
              token = m ? decodeURIComponent(m[1]) : null;
              if (/[?&]is_new=1/.test(url)) isNew = true;
            }
            if (token) {
              localStorage.setItem("qv_token", token);
              // Brand-new account → let the Feed prompt for the city on arrival.
              if (isNew) { try { localStorage.setItem("qv_pick_city", "1"); } catch (e) { /* ignore */ } }
              try {
                const { Browser } = await import("@capacitor/browser");
                await Browser.close();
              } catch (e) { /* ignore */ }
              await checkAuth();
            }
          } catch (e) { /* ignore */ }
        });
        remove = () => handle.remove();
      } catch (e) { /* ignore */ }
    })();
    return () => { if (remove) remove(); };
  }, [checkAuth]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    identifyUser(data.user?.user_id, { city: data.user?.city });
    captureEvent("login_completed", { method: "email" });
    try { localStorage.setItem("qv_user", JSON.stringify(data.user)); } catch (e) { /* ignore */ }
    return data.user;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    identifyUser(data.user?.user_id, { city: data.user?.city });
    captureEvent("signup_completed", { method: "email", city: data.user?.city || null });
    try { localStorage.setItem("qv_user", JSON.stringify(data.user)); } catch (e) { /* ignore */ }
    return data.user;
  };

  const loginWithGoogleSession = async (sessionId) => {
    const { data } = await api.post("/auth/google/session", { session_id: sessionId });
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    identifyUser(data.user?.user_id, { city: data.user?.city });
    captureEvent(data.is_new_user ? "signup_completed" : "login_completed", { method: "google" });
    try { localStorage.setItem("qv_user", JSON.stringify(data.user)); } catch (e) { /* ignore */ }
    return data.user;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) { /* ignore */ }
    localStorage.removeItem("qv_token");
    try { localStorage.removeItem("qv_user"); } catch (e) { /* ignore */ }
    setUser(null);
    resetAnalytics();
  };

  const refreshUser = async () => {
    const { data } = await api.get("/auth/me");
    setUser(data);
    return data;
  };

  // Auto-add a friend when arriving from an invite link (?add=username)
  const processPendingInvite = useCallback(async (currentUser) => {
    if (!currentUser) return;
    const uname = localStorage.getItem("qv_pending_add");
    if (!uname) return;
    localStorage.removeItem("qv_pending_add");
    if (uname === currentUser.username) return;
    try {
      const { data } = await api.post("/friends/request-by-username", { username: uname });
      if (data.status === "accepted") toast.success(`¡Ya sois amigos con @${uname}!`);
      else toast.success(`Solicitud de amistad enviada a @${uname}`);
    } catch (e) {
      // ignore invalid invite
    }
  }, []);

  useEffect(() => {
    if (user) processPendingInvite(user);
  }, [user, processPendingInvite]);

  return (
    <AuthContext.Provider
      value={{ user, setUser, loading, login, register, loginWithGoogleSession, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
