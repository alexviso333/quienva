import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { useAuth } from "@/context/AuthContext";
import { isPushSupported, subscribeToPush } from "@/lib/push";
import { Bell, Loader2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Blocking modal that asks for browser notification permission on the very
 * first login. If the user has already been asked (regardless of outcome)
 * or already granted/denied, the modal never shows.
 *
 * Design: full-screen, cannot be dismissed by clicking outside — user must
 * pick "Activar" or "Ahora no".
 */
export default function PushPermissionGate() {
  const { user, loading } = useAuth();
  const [show, setShow] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (loading || !user) {
      setShow(false);
      return;
    }
    // Only stop asking once notifications are actually granted for this user.
    const grantedKey = `qv_push_granted_${user.user_id}`;
    if (localStorage.getItem(grantedKey) === "1") {
      setShow(false);
      return;
    }
    // Users still in the intro flow (/onboarding) haven't finished setup yet —
    // don't stack this gate on top of it.
    if (localStorage.getItem("qv_onboarded") !== "1") {
      setShow(false);
      return;
    }
    if (!isPushSupported()) {
      // Browser doesn't support push — don't trap the user.
      localStorage.setItem(grantedKey, "1");
      setShow(false);
      return;
    }
    // Already granted at the browser level -> record and skip.
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      localStorage.setItem(grantedKey, "1");
      setShow(false);
      return;
    }
    // If the browser has hard-denied, we cannot force it — show the escape hatch.
    if (typeof Notification !== "undefined" && Notification.permission === "denied") {
      setFailed(true);
    }
    const timer = setTimeout(() => setShow(true), 400);
    return () => clearTimeout(timer);
  }, [user, loading]);

  const markDone = () => {
    if (user) localStorage.setItem(`qv_push_granted_${user.user_id}`, "1");
    setShow(false);
  };

  const activate = async () => {
    setSubmitting(true);
    try {
      await subscribeToPush();
      toast.success(t("push.toast_activated"));
      markDone();
    } catch (e) {
      // Could not enable (denied at OS/browser level). Let them continue.
      toast.error(e.message || t("push.toast_error"));
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  };

  if (!show) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/85 backdrop-blur-sm"
      data-testid="push-permission-gate"
    >
      <div className="relative w-full max-w-sm rounded-3xl qv-glass border border-white/10 p-6 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-qv-primary/20 flex items-center justify-center mb-4">
          <Bell className="w-8 h-8 text-qv-primary" />
        </div>
        <h2 className="font-display text-xl font-black text-white leading-tight">
          {t("push.title")}
        </h2>
        <p className="text-white/70 text-sm mt-2 leading-relaxed">
          <Trans i18nKey="push.body" components={{ strong: <span className="text-qv-secondary font-semibold" /> }} />
        </p>
        <button
          onClick={activate}
          disabled={submitting}
          className="mt-5 w-full py-3 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60"
          data-testid="push-permission-activate"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bell className="w-4 h-4" />}
          {t("push.activate")}
        </button>
        {!failed && (
          <p className="mt-3 text-white/45 text-xs leading-relaxed">
            <Trans i18nKey="push.hint" components={{ strong: <span className="text-white/70 font-semibold" /> }} />
          </p>
        )}
        {failed && (
          <>
            <p className="mt-4 text-amber-300/90 text-xs leading-relaxed">
              {t("push.blocked")}
            </p>
            <button
              onClick={markDone}
              disabled={submitting}
              className="mt-2 w-full py-2.5 rounded-2xl text-white/50 text-xs font-semibold hover:text-white/80"
              data-testid="push-permission-later"
            >
              {t("push.continue_anyway")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
