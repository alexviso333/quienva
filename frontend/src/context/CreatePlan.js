import React, { createContext, useContext, useState, useCallback } from "react";
import CreatePlanSheet from "@/components/CreatePlanSheet";

const CreatePlanContext = createContext(null);

export function useCreatePlan() {
  return useContext(CreatePlanContext) || { open: () => {} };
}

// Single app-wide plan creation sheet. Any component can call open(presetEvent, city).
export function CreatePlanProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [preset, setPreset] = useState(null);
  const [city, setCity] = useState(null);

  const openSheet = useCallback((presetEvent = null, cityArg = null) => {
    setPreset(presetEvent);
    setCity(cityArg);
    setOpen(true);
  }, []);

  return (
    <CreatePlanContext.Provider value={{ open: openSheet }}>
      {children}
      <CreatePlanSheet open={open} onOpenChange={setOpen} presetEvent={preset} city={city} />
    </CreatePlanContext.Provider>
  );
}
