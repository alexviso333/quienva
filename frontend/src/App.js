import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import PushPermissionGate from "@/components/PushPermissionGate";
import MomentGate from "@/components/MomentGate";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Feed from "@/pages/Feed";
import Friends from "@/pages/Friends";
import Notifications from "@/pages/Notifications";
import Profile from "@/pages/Profile";
import Admin from "@/pages/Admin";
import AdminMoney from "@/pages/AdminMoney";
import AdminDashboard from "@/pages/AdminDashboard";
import EventDetail from "@/pages/EventDetail";
import Onboarding from "@/pages/Onboarding";
import UserProfile from "@/pages/UserProfile";
import Chats from "@/pages/Chats";
import ChatThread from "@/pages/ChatThread";
import Rankings from "@/pages/Rankings";
import Recuerdos from "@/pages/Recuerdos";
import SettingsPage from "@/pages/Settings";
import Locales from "@/pages/Locales";
import MapPage from "@/pages/MapPage";
import NotifPrefs from "@/pages/NotifPrefs";
import Momento from "@/pages/Momento";
import { Loader2 } from "lucide-react";

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
      <Route path="/admin" element={<ProtectedRoute adminOnly><Admin /></ProtectedRoute>} />
      <Route path="/admin/dinero" element={<ProtectedRoute adminOnly><AdminMoney /></ProtectedRoute>} />
      <Route path="/admin/dashboard" element={<ProtectedRoute adminOnly><AdminDashboard /></ProtectedRoute>} />
      <Route path="/" element={<Navigate to="/feed" replace />} />
      <Route path="*" element={<Navigate to="/feed" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <PushPermissionGate />
          <MomentGate />
        </BrowserRouter>
        <Toaster position="top-center" theme="dark" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
