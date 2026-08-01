import { useEffect, useState } from "react";
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

  useEffect(() => {
    if (loading || !user) {
      setShow(false);
      return;
    }
    // Only ask once per browser per user
    const askedKey = `qv_push_asked_${user.user_id}`;
    if (localStorage.getItem(askedKey) === "1") {
      setShow(false);
      return;
    }
    if (!isPushSupported()) {
      // Browser doesn't support push — silently mark as asked so we don't loop.
      localStorage.setItem(askedKey, "1");
      setShow(false);
      return;
    }
    // Only show if the browser hasn't granted or denied yet.
    if (typeof Notification !== "undefined" && Notification.permission !== "default") {
      localStorage.setItem(askedKey, "1");
      setShow(false);
      return;
    }
    // Delay a tiny moment so we don't flash before the UI renders
    const t = setTimeout(() => setShow(true), 500);
    return () => clearTimeout(t);
  }, [user, loading]);

  const markAsked = () => {
    if (user) localStorage.setItem(`qv_push_asked_${user.user_id}`, "1");
    setShow(false);
  };

  const activate = async () => {
    setSubmitting(true);
    try {
      await subscribeToPush();
      toast.success("Notificaciones activadas ⚡");
      markAsked();
    } catch (e) {
      // User denied or something failed — record it and move on.
      toast.error(e.message || "No se pudieron activar");
      markAsked();
    } finally {
      setSubmitting(false);
    }
  };

  if (!show) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm"
      data-testid="push-permission-gate"
    >
      <div className="relative w-full max-w-sm rounded-3xl qv-glass border border-white/10 p-6 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-qv-primary/20 flex items-center justify-center mb-4">
          <Bell className="w-8 h-8 text-qv-primary" />
        </div>
        <h2 className="font-display text-xl font-black text-white leading-tight">
          Activa las notificaciones
        </h2>
        <p className="text-white/70 text-sm mt-2 leading-relaxed">
          Te avisamos cuando <span className="text-qv-secondary font-semibold">salte El Momento</span>,
          cuando un amigo diga que va a una fiesta o cuando salgan entradas nuevas.
        </p>
        <button
          onClick={activate}
          disabled={submitting}
          className="mt-5 w-full py-3 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60"
          data-testid="push-permission-activate"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bell className="w-4 h-4" />}
          Activar notificaciones
        </button>
        <button
          onClick={markAsked}
          disabled={submitting}
          className="mt-2 w-full py-2.5 rounded-2xl text-white/60 text-xs font-semibold hover:text-white/90"
          data-testid="push-permission-later"
        >
          Ahora no
        </button>
        <p className="mt-3 text-white/30 text-[10px]">
          Puedes cambiar esto luego en tu perfil.
        </p>
      </div>
    </div>
  );
}
