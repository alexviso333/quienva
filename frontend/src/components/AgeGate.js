import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

/**
 * Blocking +18 gate. Shown when a logged-in user has no birthdate on file
 * (e.g. accounts created via Google before the age gate existed). They cannot
 * use the app until they confirm they are an adult.
 */
export default function AgeGate() {
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation();
  const [birthdate, setBirthdate] = useState("");
  const [busy, setBusy] = useState(false);

  if (!user || !user.needs_birthdate) return null;

  const submit = async () => {
    if (!birthdate) {
      toast.error(t("agegate.toast_add_birthdate"));
      return;
    }
    const b = new Date(birthdate);
    const now = new Date();
    let age = now.getFullYear() - b.getFullYear();
    const m = now.getMonth() - b.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < b.getDate())) age--;
    if (isNaN(age) || age < 18) {
      toast.error(t("agegate.toast_min_age"));
      return;
    }
    setBusy(true);
    try {
      await api.put("/auth/profile", { birthdate });
      await refreshUser();
      toast.success(t("agegate.toast_verified"));
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] qv-app-bg flex flex-col justify-center px-6" data-testid="age-gate">
      <div className="max-w-md mx-auto w-full">
        <div className="w-16 h-16 rounded-full bg-qv-primary/15 border border-qv-primary/40 flex items-center justify-center mb-5">
          <ShieldCheck className="w-8 h-8 text-qv-primary" />
        </div>
        <h1 className="font-display text-3xl font-black tracking-tighter text-white">{t("agegate.title")}</h1>
        <p className="text-white/60 mt-2 leading-relaxed">
          {t("agegate.body")}
        </p>
        <label className="block text-[11px] uppercase tracking-wider text-white/40 font-bold mt-6 mb-1 ml-1">
          {t("agegate.label_birthdate")}
        </label>
        <Input
          data-testid="agegate-birthdate"
          type="date"
          value={birthdate}
          onChange={(e) => setBirthdate(e.target.value)}
          className="h-12 bg-white/5 border-white/15 rounded-2xl text-white"
        />
        <button
          data-testid="agegate-submit"
          onClick={submit}
          disabled={busy}
          className="w-full h-14 mt-4 rounded-2xl bg-qv-primary text-white font-bold text-base flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
        >
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : null} {t("agegate.confirm")}
        </button>
      </div>
    </div>
  );
}
