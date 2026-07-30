import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      setUser(null);
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
    return data.user;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const loginWithGoogleSession = async (sessionId) => {
    const { data } = await api.post("/auth/google/session", { session_id: sessionId });
    if (data.token) localStorage.setItem("qv_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {}
    localStorage.removeItem("qv_token");
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
