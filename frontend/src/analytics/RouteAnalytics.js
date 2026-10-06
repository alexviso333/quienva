import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { captureEvent } from "./posthog";

// Captures exactly one $pageview per React Router location change (SPA).
export default function RouteAnalytics() {
  const location = useLocation();
  useEffect(() => {
    const path = `${location.pathname}${location.search}`;
    captureEvent("$pageview", {
      $current_url: typeof window !== "undefined" ? window.location.href : path,
      path,
    });
  }, [location.pathname, location.search]);
  return null;
}
