import React, { createContext, useContext, useState, useCallback } from "react";
import CreatePlanSheet from "@/components/CreatePlanSheet";
import { captureEvent } from "@/analytics/posthog";

const CreatePlanContext = createContext(null);

export function useCreatePlan() {
  return useContext(CreatePlanContext) || { open: () => {}, isOpen: false };
}

// Single app-wide plan creation sheet. Any component can call open(presetEvent, city, source).
// The whole flow stays IN-APP (bottom sheet), never navigating away to a blocking page.
export function CreatePlanProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [preset, setPreset] = useState(null);
  const [city, setCity] = useState(null);
  const [source, setSource] = useState("feed");

  const openSheet = useCallback((presetEvent = null, cityArg = null, src = "feed") => {
    setPreset(presetEvent);
    setCity(cityArg);
    setSource(src);
    setOpen(true);
    captureEvent("plan_create_started", { source: presetEvent ? "event" : src });
  }, []);

  return (
    <CreatePlanContext.Provider value={{ open: openSheet, isOpen: open }}>
      {children}
      <CreatePlanSheet open={open} onOpenChange={setOpen} presetEvent={preset} city={city} source={source} />
    </CreatePlanContext.Provider>
  );
}
