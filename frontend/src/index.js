import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import "@/index.css";
import "@/i18n";
import App from "@/App";
import { isNativeApp } from "@/lib/platform";

// --- Native app: lock zoom -----------------------------------------------------
// Inside the iOS/Android app the WKWebView must behave like a native screen, not
// a zoomable web page. Without this, a double-tap zooms in, pinch zooms, and
// focusing a text field auto-zooms and "cuts off" the layout. We ONLY do this in
// the native app so the website (quienva.me) keeps its normal, zoomable behavior.
if (isNativeApp()) {
  const vp = document.querySelector('meta[name="viewport"]');
  if (vp) {
    vp.setAttribute(
      "content",
      "width=device-width, initial-scale=1, maximum-scale=1, minimum-scale=1, user-scalable=no, viewport-fit=cover",
    );
  }
  // Kills the 300ms double-tap-to-zoom gesture entirely.
  document.documentElement.style.touchAction = "manipulation";
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data is considered fresh for 5 min — no refetch when re-visiting a page.
      staleTime: 5 * 60_000,
      // Keep unused query data in cache for 24h → back navigation is instant AND
      // the offline snapshot below survives long idle periods.
      gcTime: 24 * 60 * 60_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: "always",
      retry: 1,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    },
    mutations: {
      retry: 0,
    },
  },
});

// --- Offline cache -----------------------------------------------------------
// Persist the last-seen party data to localStorage so the app opens INSTANTLY
// (showing the last fiestas) even with poor/no connectivity, then quietly
// refreshes in the background. Only browsing content is persisted (never
// admin, friends, chats or notifications) to keep it small and private.
const OFFLINE_KEYS = [
  "events",
  "events-min",
  "carousels",
  "top-weekend",
  "genres",
  "event",
  "discover",
  "past-events",
  "cities",
  "stories",
];

const persister = createSyncStoragePersister({
  storage: window.localStorage,
  key: "qv-offline-cache",
  throttleTime: 1000,
});

const persistOptions = {
  persister,
  maxAge: 24 * 60 * 60_000, // keep offline snapshot for 24h
  buster: "v1", // bump to discard old snapshots on a breaking release
  dehydrateOptions: {
    shouldDehydrateQuery: (query) => {
      if (query.state.status !== "success") return false;
      const key = Array.isArray(query.queryKey) ? query.queryKey[0] : query.queryKey;
      return OFFLINE_KEYS.includes(key);
    },
  },
};

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <App />
    </PersistQueryClientProvider>
  </React.StrictMode>,
);

// Register service worker for PWA + Web Push
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  });
}
