import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import { isPushSupported, subscribeToPush } from "@/lib/push";
import { Bell, Loader2, X } from "lucide-react";
import { toast } from "sonner";

/**
 * NON-BLOCKING notification prompt (spec 1.4).
 *
 * Previously a full-screen modal (z-[100] fixed inset-0) that intercepted every
 * click and blocked the whole UI. Now it's a slim banner anchored at the bottom
 * (above the bottom nav) that NEVER covers the screen: the wrapper is
 * pointer-events-none so taps pass through everywhere except the banner itself.
 *
 * Behaviour:
 *  - Only shows once onboarded, push is supported, and permission isn't granted.
 *  - "Activar" asks the browser for permission.
 *  - X dismisses and snoozes the banner for 7 days (per user).
 */
const SNOOZE_DAYS = 7;

export default function PushPermissionGate() {
  const { t } = useTranslation();
  const { user, loading } = useAuth();
  const [show, setShow] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (loading || !user) {
      setShow(false);
      return;
    }
    const grantedKey = `qv_push_granted_${user.user_id}`;
    const snoozeKey = `qv_push_snooze_until_${user.user_id}`;
    if (localStorage.getItem(grantedKey) === "1") {
      setShow(false);
      return;
    }
    // Still in the intro flow — don't stack on top of onboarding.
    if (localStorage.getItem("qv_onboarded") !== "1") {
      setShow(false);
      return;
    }
    if (!isPushSupported()) {
      localStorage.setItem(grantedKey, "1");
      setShow(false);
      return;
    }
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      localStorage.setItem(grantedKey, "1");
      setShow(false);
      return;
    }
    // Snoozed (user tapped X within the last 7 days) — stay quiet.
    const snoozeUntil = Number(localStorage.getItem(snoozeKey) || 0);
    if (snoozeUntil && Date.now() < snoozeUntil) {
      setShow(false);
      return;
    }
    const timer = setTimeout(() => setShow(true), 1200);
    return () => clearTimeout(timer);
  }, [user, loading]);

  const dismiss = () => {
    if (user) {
      localStorage.setItem(
        `qv_push_snooze_until_${user.user_id}`,
        String(Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000)
      );
    }
    setShow(false);
  };

  const activate = async () => {
    setSubmitting(true);
    try {
      await subscribeToPush();
      toast.success(t("push.toast_activated"));
      if (user) localStorage.setItem(`qv_push_granted_${user.user_id}`, "1");
      setShow(false);
    } catch (e) {
      toast.error(e.message || t("push.toast_error"));
      // Can't enable (denied at browser level) — snooze so we don't nag.
      dismiss();
    } finally {
      setSubmitting(false);
    }
  };

  if (!show) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-[78px] lg:bottom-5 z-40 px-3"
      data-testid="push-permission-gate"
    >
      <div className="pointer-events-auto mx-auto max-w-md flex items-center gap-3 rounded-2xl qv-glass border border-white/12 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.8)] p-3">
        <div className="w-9 h-9 rounded-full bg-qv-primary/20 flex items-center justify-center shrink-0">
          <Bell className="w-4 h-4 text-qv-primary" />
        </div>
        <p className="flex-1 min-w-0 text-[13px] leading-tight text-white/85">
          {t("push.banner_text", "Activa los avisos para no perderte los planes de tu grupo.")}
        </p>
        <button
          onClick={activate}
          disabled={submitting}
          data-testid="push-permission-activate"
          className="qv-btn shrink-0 h-9 px-4 rounded-full bg-qv-primary text-white text-xs font-bold flex items-center justify-center gap-1.5 disabled:opacity-60"
        >
          {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          {t("push.activate_short", "Activar")}
        </button>
        <button
          onClick={dismiss}
          disabled={submitting}
          data-testid="push-permission-dismiss"
          aria-label={t("feed.dismiss", "Cerrar")}
          className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white/45 hover:text-white/80 active:scale-90"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
