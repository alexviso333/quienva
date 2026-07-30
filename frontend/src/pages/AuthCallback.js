import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";

export default function AuthCallback() {
  const { loginWithGoogleSession } = useAuth();
  const navigate = useNavigate();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash;
    const match = hash.match(/session_id=([^&]+)/);
    const sessionId = match ? decodeURIComponent(match[1]) : null;

    (async () => {
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
  }, [loginWithGoogleSession, navigate]);

  return (
    <div className="min-h-screen qv-app-bg flex items-center justify-center" data-testid="auth-callback">
      <Loader2 className="w-8 h-8 text-qv-primary animate-spin" />
    </div>
  );
}
