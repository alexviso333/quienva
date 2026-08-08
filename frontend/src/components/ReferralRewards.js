import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Trophy, Star } from "lucide-react";
import api from "@/lib/api";
import InviteGroup from "@/components/InviteGroup";

const MILESTONES = [1, 3, 5, 10];
const BADGE_KEYS = {
  1: "referral.badge_1",
  3: "referral.badge_3",
  5: "referral.badge_5",
  10: "referral.badge_10",
};

// Ambassador rewards: gamifies inviting with points + level badges based on how
// many friends you've brought (uses existing /me/referral data — no perks that
// require owning a venue). Status is the reward.
export default function ReferralRewards({ className = "" }) {
  const { t } = useTranslation();
  const { data: referral } = useQuery({
    queryKey: ["referral"],
    queryFn: async () => (await api.get("/me/referral")).data,
    staleTime: 5 * 60_000,
  });

  const count = referral?.referred_count || 0;
  const perReferral = referral?.points_per_referral || 0;
  const points = count * perReferral;
  const next = MILESTONES.find((m) => m > count);
  const nextBadge = next ? t(BADGE_KEYS[next]) : null;
  const prev = [...MILESTONES].reverse().find((m) => m <= count) || 0;
  const span = next ? next - prev : 1;
  const progress = next ? Math.min(100, Math.round(((count - prev) / span) * 100)) : 100;

  return (
    <div className={`rounded-2xl border border-white/10 bg-white/[0.04] p-4 flex flex-col gap-4 ${className}`} data-testid="referral-rewards">
      <div className="flex items-center gap-2">
        <Trophy className="w-5 h-5 text-yellow-300 shrink-0" />
        <div>
          <p className="font-display font-black text-white">{t("referral.title")}</p>
          <p className="text-white/55 text-xs">{t("referral.subtitle")}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-white/5 p-3 text-center">
          <p className="text-2xl font-black text-qv-primary" data-testid="referral-count">{count}</p>
          <p className="text-[11px] uppercase tracking-wide text-white/50 font-bold">{t("referral.friends_invited")}</p>
        </div>
        <div className="rounded-xl bg-white/5 p-3 text-center">
          <p className="text-2xl font-black text-qv-secondary">{points}</p>
          <p className="text-[11px] uppercase tracking-wide text-white/50 font-bold">{t("referral.points")}</p>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-white/60 font-semibold flex items-center gap-1"><Star className="w-3.5 h-3.5 text-yellow-300" /> {t("referral.next_badge")}</span>
          <span className="text-white font-bold text-right">{next ? t("referral.to_next", { count: next - count, badge: nextBadge }) : t("referral.maxed")}</span>
        </div>
        <div className="h-2 rounded-full bg-white/10 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-qv-primary to-qv-secondary transition-all" style={{ width: `${progress}%` }} />
        </div>
        <div className="flex justify-between mt-2 gap-1">
          {MILESTONES.map((m) => (
            <div
              key={m}
              className={`flex-1 text-center text-[10px] font-bold rounded-lg py-1 leading-tight ${count >= m ? "bg-qv-primary/20 text-qv-primary" : "bg-white/5 text-white/40"}`}
            >
              {m}·{t(BADGE_KEYS[m])}
            </div>
          ))}
        </div>
      </div>

      <InviteGroup />
    </div>
  );
}
