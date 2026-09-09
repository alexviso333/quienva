import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { Loader2 } from "lucide-react";

export default function AuthCallback() {
  const { loginWithGoogleSession, setUser } = useAuth();
  const navigate = useNavigate();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    (async () => {
      // 1) Self-hosted Google OAuth: ?code=... in the query string
      const search = new URLSearchParams(window.location.search);
      const code = search.get("code");
      const isNativeLogin = search.get("state") === "native";
      if (code) {
        try {
          const redirectUri = window.location.origin + "/auth/callback";
          // Inherit the city the guest was exploring (validated server-side; used
          // only when creating a brand-new account).
          let guestCity = null;
          try { guestCity = localStorage.getItem("qv_guest_city") || null; } catch { /* ignore */ }
          const { data } = await api.post("/auth/google/callback", {
            code,
            redirect_uri: redirectUri,
            guest_city: guestCity,
          });
          // NATIVE app login: this page is running in the phone's Safari, so we
          // bounce the session token back INTO the app via its custom URL scheme.
          if (isNativeLogin && data.token) {
            window.location.href = `quienva://auth-callback?token=${encodeURIComponent(data.token)}`;
            return;
          }
          if (data.token) localStorage.setItem("qv_token", data.token);
          setUser(data.user);
          window.history.replaceState(null, "", "/feed");
          const onboarded = localStorage.getItem("qv_onboarded") === "1";
          navigate(onboarded ? "/feed" : "/onboarding", { replace: true });
          return;
        } catch (e) {
          navigate("/login", { replace: true });
          return;
        }
      }

      // 2) Legacy Emergent OAuth (kept for backward compatibility): #session_id=...
      const hash = window.location.hash;
      const match = hash.match(/session_id=([^&]+)/);
      const sessionId = match ? decodeURIComponent(match[1]) : null;
      if (!sessionId) {
        navigate("/login", { replace: true });
        return;
      }
      try {
        await loginWithGoogleSession(sessionId);
        window.history.replaceState(null, "", "/feed");
        navigate("/feed", { replace: true });
      } catch (e) {
        navigate("/login", { replace: true });
      }
    })();
  }, [loginWithGoogleSession, setUser, navigate]);

  return (
    <div className="min-h-screen qv-app-bg flex items-center justify-center" data-testid="auth-callback">
      <Loader2 className="w-8 h-8 text-qv-primary animate-spin" />
    </div>
  );
}
