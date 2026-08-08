import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Settings, Trophy, Archive, Share2, Shield, LayoutDashboard, Sparkles, ChevronRight } from "lucide-react";
import { BadgesPanel } from "@/components/BadgesPanel";
import ReferralRewards from "@/components/ReferralRewards";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();

  // Show the Wrapped banner only if LAST month had activity (defaults to last month).
  const { data: wrapped } = useQuery({
    queryKey: ["wrapped-banner"],
    queryFn: async () => (await api.get("/me/wrapped")).data,
    staleTime: 5 * 60 * 1000,
  });
  const showWrapped = !!wrapped?.has_data;

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-2 flex items-center justify-between">
        <h1 className="font-display text-4xl font-black tracking-tighter">
          {t("profile.title")}<span className="text-qv-primary">.</span>
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

      {/* Wrapped — monthly recap (only shown if last month had activity) */}
      {showWrapped && (
      <div className="px-5 mb-5">
        <button
          data-testid="wrapped-banner"
          onClick={() => navigate("/wrapped")}
          className="w-full rounded-3xl p-4 flex items-center gap-3 bg-gradient-to-r from-qv-primary/25 via-qv-secondary/20 to-yellow-300/15 border border-white/10 active:scale-[0.98] transition-transform text-left"
        >
          <div className="w-11 h-11 rounded-2xl bg-black/30 flex items-center justify-center shrink-0">
            <Sparkles className="w-6 h-6 text-yellow-300" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-display font-black text-white text-lg leading-tight">{t("profile.wrapped_title", { month: wrapped?.month_label })}</p>
            <p className="text-white/60 text-xs">{t("profile.wrapped_sub")}</p>
          </div>
          <ChevronRight className="w-5 h-5 text-white/50 shrink-0" />
        </button>
      </div>
      )}

      {/* Quick actions */}
      <div className="px-5 grid grid-cols-4 gap-2 mb-5">
        <QuickAction testid="qa-recuerdos" icon={Archive} label={t("profile.qa_memories")} color="bg-qv-secondary/20 text-qv-secondary" onClick={() => navigate("/recuerdos")} />
        <QuickAction testid="qa-ranking" icon={Trophy} label={t("profile.qa_ranking")} color="bg-yellow-300/20 text-yellow-200" onClick={() => navigate("/top")} />
        <QuickAction testid="qa-invitar" icon={Share2} label={t("profile.qa_invite")} color="bg-qv-primary/20 text-qv-primary" onClick={() => navigate("/ajustes")} />
        <QuickAction testid="qa-ajustes" icon={Settings} label={t("profile.qa_settings")} color="bg-white/10 text-white/80" onClick={() => navigate("/ajustes")} />
      </div>

      {/* Ambassador / referral rewards */}
      <div className="px-5 mb-5">
        <ReferralRewards />
      </div>

      {/* Badges (compact) */}
      <div className="px-5 mb-5">
        <BadgesPanel compact />
      </div>

      {/* Admin */}
      {user?.role === "admin" && (
        <div className="px-5 flex flex-col gap-3 pb-6">
          <p className="text-xs uppercase tracking-widest text-white/40 font-bold">{t("profile.admin")}</p>
          <button
            data-testid="admin-dashboard-btn"
            onClick={() => navigate("/admin/dashboard")}
            className="h-12 rounded-2xl bg-qv-secondary/15 border border-qv-secondary/40 text-qv-secondary font-semibold flex items-center justify-center gap-2 active:scale-95"
          >
            <LayoutDashboard className="w-4 h-4" /> {t("profile.admin_dashboard")}
          </button>
          <button
            data-testid="admin-panel-btn"
            onClick={() => navigate("/admin")}
            className="h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95"
          >
            <Shield className="w-4 h-4" /> {t("profile.admin_manage")}
          </button>
        </div>
      )}
    </AppShell>
  );
}
