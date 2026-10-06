import "@/App.css";
import { lazy, Suspense, useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import api from "@/lib/api";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { GuestGateProvider } from "@/context/GuestGate";
import { CreatePlanProvider } from "@/context/CreatePlan";
import PushPermissionGate from "@/components/PushPermissionGate";
import MomentGate from "@/components/MomentGate";
import AgeGate from "@/components/AgeGate";
import InviteNudgeGate from "@/components/InviteNudgeGate";
import OfflineBanner from "@/components/OfflineBanner";
import { Loader2 } from "lucide-react";
import { initAnalytics, identifyUser, resetAnalytics, captureEvent } from "@/analytics/posthog";
// Eager: first-paint / auth-critical screens.
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Feed from "@/pages/Feed";
import TrackRedirect from "@/pages/TrackRedirect";
// Lazy: split every other route into its own chunk so the initial bundle stays
// small (notably faster first load, especially on mobile / Vercel free tier).
// Pure performance change — no behavior or UI difference.
const Friends = lazy(() => import("@/pages/Friends"));
const Notifications = lazy(() => import("@/pages/Notifications"));
const Profile = lazy(() => import("@/pages/Profile"));
const Admin = lazy(() => import("@/pages/Admin"));
const AdminMoney = lazy(() => import("@/pages/AdminMoney"));
const AdminDashboard = lazy(() => import("@/pages/AdminDashboard"));
const EventDetail = lazy(() => import("@/pages/EventDetail"));
const Onboarding = lazy(() => import("@/pages/Onboarding"));
const UserProfile = lazy(() => import("@/pages/UserProfile"));
const Chats = lazy(() => import("@/pages/Chats"));
const ChatThread = lazy(() => import("@/pages/ChatThread"));
const Rankings = lazy(() => import("@/pages/Rankings"));
const Recuerdos = lazy(() => import("@/pages/Recuerdos"));
const SettingsPage = lazy(() => import("@/pages/Settings"));
const Locales = lazy(() => import("@/pages/Locales"));
const MapPage = lazy(() => import("@/pages/MapPage"));
const NotifPrefs = lazy(() => import("@/pages/NotifPrefs"));
const Momento = lazy(() => import("@/pages/Momento"));
const Descubrir = lazy(() => import("@/pages/Descubrir"));
const Wrapped = lazy(() => import("@/pages/Wrapped"));
const PlanView = lazy(() => import("@/pages/PlanView"));

function LoadingScreen() {
  return (
    <div className="min-h-screen qv-app-bg flex items-center justify-center" data-testid="loading-screen">
      <Loader2 className="w-8 h-8 text-qv-primary animate-spin" />
    </div>
  );
}

function ProtectedRoute({ children, adminOnly }) {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/feed" replace />;
  return children;
}

// Open to everyone. Guests get read-only content; the app pops a registration
// gate only when they try a social action. Authenticated users see it normally.
function PublicRoute({ children }) {
  const { loading } = useAuth();
  if (loading) return <LoadingScreen />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  const { user } = useAuth();
  const qc = useQueryClient();
  const claimingGroup = useRef(false);
  // Analytics (PostHog): init once, identify on auth, reset on logout.
  useEffect(() => { initAnalytics(); }, []);
  // Retention signal: app_opened once per mount, with days since last open.
  useEffect(() => {
    try {
      const last = parseInt(localStorage.getItem("qv_last_open") || "0", 10);
      const nowMs = Date.now();
      const days = last ? Math.floor((nowMs - last) / 86400000) : null;
      captureEvent("app_opened", { days_since_last: days });
      localStorage.setItem("qv_last_open", String(nowMs));
    } catch (e) { /* ignore */ }
  }, []);
  const prevUserRef = useRef(null);
  useEffect(() => {
    const uid = user?.id || user?.user_id;
    if (uid) {
      identifyUser(uid, { username: user?.username, city: user?.city });
      prevUserRef.current = uid;
    } else if (prevUserRef.current) {
      resetAnalytics();
      prevUserRef.current = null;
    }
  }, [user]);
  // Manual SPA pageview on every route change.
  useEffect(() => {
    captureEvent("$pageview", {
      $current_url: typeof window !== "undefined" ? window.location.href : location.pathname,
      path: `${location.pathname}${location.search}`,
    });
  }, [location.pathname, location.search]);
  // Capture referral / invite params on ANY route the visitor lands on. This
  // lets us send shared links to the app ROOT (preview) instead of /login —
  // the code is persisted and applied when the guest eventually signs up.
  useEffect(() => {
    try {
      const params = new URLSearchParams(location.search);
      const ref = params.get("ref");
      if (ref) localStorage.setItem("qv_pending_ref", ref.trim());
      const add = params.get("add");
      if (add) localStorage.setItem("qv_pending_add", add.toLowerCase().trim());
      const grp = params.get("g");
      if (grp) localStorage.setItem("qv_pending_group", grp.trim());
    } catch (e) { /* ignore */ }
  }, [location.search]);
  // Once the visitor is authenticated (via ANY path: email, Google, Apple), if a
  // group invite is pending, claim it — auto-join the group + auto-friend the
  // crew. Robust single place so no auth entrypoint misses it.
  useEffect(() => {
    if (!user) return;
    let pendingGrp;
    try { pendingGrp = localStorage.getItem("qv_pending_group"); } catch (e) { return; }
    if (!pendingGrp || claimingGroup.current) return;
    claimingGroup.current = true;
    (async () => {
      try {
        const { data } = await api.post("/me/claim-group-invite", { code: pendingGrp });
        if (data?.ok && !data?.already_member) {
          toast.success("¡Te has unido al grupo! 🎉");
          qc.invalidateQueries({ queryKey: ["groups"] });
          qc.invalidateQueries({ queryKey: ["friends"] });
        }
      } catch (e) { /* ignore — code invalid/expired */ }
      finally {
        try { localStorage.removeItem("qv_pending_group"); } catch (e) { /* ignore */ }
        claimingGroup.current = false;
      }
    })();
  }, [user, qc]);
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/ig" element={<TrackRedirect source="ig" />} />
        <Route path="/tt" element={<TrackRedirect source="tt" />} />
        <Route path="/r/:src" element={<TrackRedirect />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
        <Route path="/feed" element={<PublicRoute><Feed /></PublicRoute>} />
        <Route path="/event/:id" element={<PublicRoute><EventDetail /></PublicRoute>} />
        <Route path="/p/:slug" element={<PublicRoute><PlanView /></PublicRoute>} />
        <Route path="/plan/:slug" element={<PublicRoute><PlanView /></PublicRoute>} />
        <Route path="/friends" element={<ProtectedRoute><Friends /></ProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
        <Route path="/novedades" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route path="/users/:userId" element={<ProtectedRoute><UserProfile /></ProtectedRoute>} />
        <Route path="/chats" element={<ProtectedRoute><Chats /></ProtectedRoute>} />
        <Route path="/chats/dm/:id" element={<ProtectedRoute><ChatThread kind="dm" /></ProtectedRoute>} />
        <Route path="/chats/group/:id" element={<ProtectedRoute><ChatThread kind="group" /></ProtectedRoute>} />
        <Route path="/top" element={<ProtectedRoute><Rankings /></ProtectedRoute>} />
        <Route path="/memories" element={<Navigate to="/recuerdos" replace />} />
        <Route path="/fiestas-pasadas" element={<Navigate to="/recuerdos" replace />} />
        <Route path="/recuerdos" element={<ProtectedRoute><Recuerdos /></ProtectedRoute>} />
        <Route path="/ajustes" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
        <Route path="/locales" element={<PublicRoute><Locales /></PublicRoute>} />
        <Route path="/mapa" element={<PublicRoute><MapPage /></PublicRoute>} />
        <Route path="/ajustes/avisos" element={<ProtectedRoute><NotifPrefs /></ProtectedRoute>} />
        <Route path="/momento" element={<ProtectedRoute><Momento /></ProtectedRoute>} />
        <Route path="/descubrir" element={<ProtectedRoute><Descubrir /></ProtectedRoute>} />
        {/* Sprint 5: "Momentos" (galería huérfana, sin enlaces) consolidada en Recuerdos */}
        <Route path="/momentos" element={<Navigate to="/recuerdos" replace />} />
        <Route path="/wrapped" element={<ProtectedRoute><Wrapped /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute adminOnly><Admin /></ProtectedRoute>} />
        <Route path="/admin/dinero" element={<ProtectedRoute adminOnly><AdminMoney /></ProtectedRoute>} />
        <Route path="/admin/dashboard" element={<ProtectedRoute adminOnly><AdminDashboard /></ProtectedRoute>} />
        <Route path="/" element={<Navigate to="/feed" replace />} />
        <Route path="*" element={<Navigate to="/feed" replace />} />
      </Routes>
    </Suspense>
  );
}

function App() {
  // Hide the native launch overlay (#qv-splash, injected in index.html) once the
  // React app has mounted, with a smooth fade. No-op on the web (the overlay is
  // display:none there). A safety timeout guarantees it never gets stuck.
  useEffect(() => {
    const el = document.getElementById("qv-splash");
    if (!el) return;
    const hide = () => {
      el.classList.add("qv-hide");
      setTimeout(() => el.remove(), 600);
    };
    const timer = setTimeout(hide, 550);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <GuestGateProvider>
            <CreatePlanProvider>
              <AppRouter />
              <OfflineBanner />
              <PushPermissionGate />
              <MomentGate />
              <AgeGate />
              <InviteNudgeGate />
            </CreatePlanProvider>
          </GuestGateProvider>
        </BrowserRouter>
        <Toaster position="top-center" theme="dark" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
