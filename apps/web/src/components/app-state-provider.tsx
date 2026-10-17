"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface AppState {
  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const value = useMemo(
    () => ({ activeConversationId, setActiveConversationId }),
    [activeConversationId],
  );
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within an AppStateProvider");
  return ctx;
}
