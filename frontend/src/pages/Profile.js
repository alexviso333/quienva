import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Settings, Trophy, Archive, Share2, Shield, LayoutDashboard } from "lucide-react";
import { BadgesPanel } from "@/components/BadgesPanel";

function QuickAction({ icon: Icon, label, onClick, color, testid }) {
  return (
    <button
      onClick={onClick}
      data-testid={testid}
      className="flex flex-col items-center justify-center gap-1.5 rounded-2xl bg-white/[0.04] border border-white/10 py-3 active:scale-95 transition-transform"
    >
      <div className={`w-10 h-10 rounded-full flex items-center justify-center ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <span className="text-[11px] font-bold text-white/80">{label}</span>
    </button>
  );
}

export default function Profile() {
  const { user } = useAuth();
  const navigate = useNavigate();

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-2 flex items-center justify-between">
        <h1 className="font-display text-4xl font-black tracking-tighter">
          Perfil<span className="text-qv-primary">.</span>
        </h1>
        <button
          data-testid="settings-btn"
          onClick={() => navigate("/ajustes")}
          className="w-11 h-11 rounded-full qv-glass border border-white/15 flex items-center justify-center active:scale-90"
        >
          <Settings className="w-5 h-5 text-white" />
        </button>
      </header>

      {/* Identity */}
      <div className="px-5 flex items-center gap-4 pt-2 pb-5">
        <AvatarCircle name={user?.name} picture={user?.picture} size={72} ring={false} testid="profile-avatar" />
        <div className="min-w-0">
          <p className="text-xl font-bold truncate">{user?.name}</p>
          <p className="text-white/40 text-sm truncate">@{user?.username}</p>
          <p className="text-white/40 text-xs mt-0.5">{user?.city}</p>
        </div>
      </div>

      {/* Quick actions */}
      <div className="px-5 grid grid-cols-4 gap-2 mb-5">
        <QuickAction testid="qa-recuerdos" icon={Archive} label="Recuerdos" color="bg-qv-secondary/20 text-qv-secondary" onClick={() => navigate("/recuerdos")} />
        <QuickAction testid="qa-ranking" icon={Trophy} label="Ranking" color="bg-yellow-300/20 text-yellow-200" onClick={() => navigate("/top")} />
        <QuickAction testid="qa-invitar" icon={Share2} label="Invitar" color="bg-qv-primary/20 text-qv-primary" onClick={() => navigate("/ajustes")} />
        <QuickAction testid="qa-ajustes" icon={Settings} label="Ajustes" color="bg-white/10 text-white/80" onClick={() => navigate("/ajustes")} />
      </div>

      {/* Badges (compact) */}
      <div className="px-5 mb-5">
        <BadgesPanel compact />
      </div>

      {/* Admin */}
      {user?.role === "admin" && (
        <div className="px-5 flex flex-col gap-3 pb-6">
          <p className="text-xs uppercase tracking-widest text-white/40 font-bold">Administración</p>
          <button
            data-testid="admin-dashboard-btn"
            onClick={() => navigate("/admin/dashboard")}
            className="h-12 rounded-2xl bg-qv-secondary/15 border border-qv-secondary/40 text-qv-secondary font-semibold flex items-center justify-center gap-2 active:scale-95"
          >
            <LayoutDashboard className="w-4 h-4" /> Panel de control
          </button>
          <button
            data-testid="admin-panel-btn"
            onClick={() => navigate("/admin")}
            className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95"
          >
            <Shield className="w-4 h-4" /> Gestionar fiestas
          </button>
        </div>
      )}
    </AppShell>
  );
}
