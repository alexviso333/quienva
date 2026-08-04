import "@/App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import PushPermissionGate from "@/components/PushPermissionGate";
import MomentGate from "@/components/MomentGate";
import AgeGate from "@/components/AgeGate";
import OfflineBanner from "@/components/OfflineBanner";
import { Loader2 } from "lucide-react";
// Eager: first-paint / auth-critical screens.
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Feed from "@/pages/Feed";
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

function AppRouter() {
  const location = useLocation();
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
        <Route path="/feed" element={<ProtectedRoute><Feed /></ProtectedRoute>} />
        <Route path="/event/:id" element={<ProtectedRoute><EventDetail /></ProtectedRoute>} />
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
        <Route path="/locales" element={<ProtectedRoute><Locales /></ProtectedRoute>} />
        <Route path="/mapa" element={<ProtectedRoute><MapPage /></ProtectedRoute>} />
        <Route path="/ajustes/avisos" element={<ProtectedRoute><NotifPrefs /></ProtectedRoute>} />
        <Route path="/momento" element={<ProtectedRoute><Momento /></ProtectedRoute>} />
        <Route path="/descubrir" element={<ProtectedRoute><Descubrir /></ProtectedRoute>} />
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
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <OfflineBanner />
          <PushPermissionGate />
          <MomentGate />
          <AgeGate />
        </BrowserRouter>
        <Toaster position="top-center" theme="dark" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
