import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";

/**
 * Subtle top strip shown when the device is offline. The app keeps working
 * from the persisted React Query cache (last-seen fiestas), so we just let the
 * user know what they're looking at is the cached version.
 */
export default function OfflineBanner() {
  const [offline, setOffline] = useState(
    typeof navigator !== "undefined" && navigator.onLine === false
  );

  useEffect(() => {
    const goOnline = () => setOffline(false);
    const goOffline = () => setOffline(true);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      data-testid="offline-banner"
      className="fixed top-0 inset-x-0 z-[100] flex items-center justify-center gap-1.5 bg-amber-400/90 px-3 py-1 text-center text-[11px] font-semibold text-black backdrop-blur-sm"
      role="status"
    >
      <WifiOff className="w-3.5 h-3.5 shrink-0" />
      Sin conexión — mostrando lo último
    </div>
  );
}
