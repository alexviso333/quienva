import { useState, useEffect, useCallback } from "react";

/**
 * Shared geolocation hook. Returns the viewer's [lat, lng] once granted, plus
 * the current state and a `locate()` trigger. Used by the map and the Locales
 * list so both can show distances from the user.
 */
export function useMyLocation({ auto = true } = {}) {
  const [pos, setPos] = useState(null); // [lat, lng]
  const [state, setState] = useState("idle"); // idle | locating | ok | denied | unsupported

  const locate = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setState("unsupported");
      return;
    }
    setState("locating");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos([p.coords.latitude, p.coords.longitude]);
        setState("ok");
      },
      () => setState("denied"),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }, []);

  useEffect(() => {
    if (auto) locate();
  }, [auto, locate]);

  return { pos, state, locate };
}
