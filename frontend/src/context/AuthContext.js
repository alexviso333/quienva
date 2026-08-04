import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

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
      const { data } = await api.get("/auth/me");
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

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    try { localStorage.setItem("qv_user", JSON.stringify(data.user)); } catch (e) { /* ignore */ }
    return data.user;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    try { localStorage.setItem("qv_user", JSON.stringify(data.user)); } catch (e) { /* ignore */ }
    return data.user;
  };

  const loginWithGoogleSession = async (sessionId) => {
    const { data } = await api.post("/auth/google/session", { session_id: sessionId });
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
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
