import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import { Users, UserPlus, PartyPopper, X, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import GroupInviteStep from "@/components/GroupInviteStep";

/**
 * Skippable blocking popup shown when an admin sends the user an "invite your
 * friends" nudge (user.invite_nudge.active === true). Depending on the nudge
 * action it offers creating/inviting a group, finding friends by contacts, or
 * both. The user can always dismiss it ("Ahora no").
 */
export default function InviteNudgeGate() {
  const { user, setUser } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [hidden, setHidden] = useState(false);

  const nudge = user?.invite_nudge;
  if (!user || !nudge || !nudge.active || hidden) return null;

  const action = nudge.action || "both";
  const showGroup = action === "group" || action === "both";
  const showFriends = action === "friends" || action === "both";

  const dismiss = async () => {
    setHidden(true);
    try { await api.post("/me/invite-nudge/dismiss"); } catch (e) { /* ignore */ }
    setUser((u) => (u ? { ...u, invite_nudge: null } : u));
  };

  const goFriends = async () => {
    await dismiss();
    navigate("/friends");
  };

  return (
    <div className="fixed inset-0 z-[75] bg-black/75 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="invite-nudge-gate">
      <div className="w-full max-w-md bg-[#121215] border border-white/10 rounded-t-3xl sm:rounded-3xl p-6 pt-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] max-h-[92vh] overflow-y-auto hide-scrollbar">
        <div className="flex justify-end -mt-1 -mr-1">
          <button
            onClick={dismiss}
            data-testid="invite-nudge-close"
            aria-label={t("nudge.skip", "Ahora no")}
            className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center text-white/70 active:scale-90"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="text-center flex flex-col items-center gap-3 -mt-3 mb-5">
          <div className="w-16 h-16 rounded-full bg-qv-primary/15 border border-qv-primary/40 flex items-center justify-center">
            <PartyPopper className="w-8 h-8 text-qv-primary" />
          </div>
          <h1 className="font-display text-2xl font-black text-white leading-tight">
            {t("nudge.title", "Trae a tu gente 🎉")}
          </h1>
          <p className="text-white/65 text-sm leading-relaxed max-w-xs">
            {nudge.body || t("nudge.default_body", "Invita a tus amigos y vivid el finde juntos.")}
          </p>
        </div>

        {showGroup && (
          <div className="mb-2">
            <p className="flex items-center gap-2 text-white font-bold text-sm mb-3">
              <Users className="w-4 h-4 text-qv-primary" /> {t("nudge.group_title", "Monta tu grupo")}
            </p>
            <GroupInviteStep />
          </div>
        )}

        {showGroup && showFriends && (
          <div className="flex items-center gap-3 my-4">
            <span className="flex-1 h-px bg-white/10" />
            <span className="text-white/35 text-xs uppercase tracking-widest">{t("nudge.or", "o")}</span>
            <span className="flex-1 h-px bg-white/10" />
          </div>
        )}

        {showFriends && (
          <button
            onClick={goFriends}
            data-testid="invite-nudge-friends"
            className="w-full h-14 rounded-2xl bg-qv-secondary/15 border border-qv-secondary/40 text-white font-bold flex items-center justify-center gap-2 active:scale-95"
          >
            <UserPlus className="w-5 h-5 text-qv-secondary" />
            {t("nudge.friends_btn", "Buscar amigos en mis contactos")}
            <ChevronRight className="w-4 h-4 text-white/50" />
          </button>
        )}

        <button
          onClick={dismiss}
          data-testid="invite-nudge-skip"
          className="w-full h-11 mt-3 text-white/45 text-sm font-semibold active:scale-95"
        >
          {t("nudge.skip", "Ahora no")}
        </button>
      </div>
    </div>
  );
}
