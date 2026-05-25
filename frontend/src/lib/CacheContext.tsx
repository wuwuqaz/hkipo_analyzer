"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { LiveResultsResponse, HistoryListResponse } from "./types";

interface CacheState {
  liveData: LiveResultsResponse | null;
  historyData: HistoryListResponse | null;
}

interface CacheContextValue extends CacheState {
  setLiveData: (data: LiveResultsResponse) => void;
  setHistoryData: (data: HistoryListResponse) => void;
  invalidate: () => void;
}

const CacheContext = createContext<CacheContextValue | null>(null);

export function CacheProvider({ children }: { children: ReactNode }) {
  const [cache, setCache] = useState<CacheState>({ liveData: null, historyData: null });

  const setLiveData = useCallback((data: LiveResultsResponse) => {
    setCache((prev) => ({ ...prev, liveData: data }));
  }, []);

  const setHistoryData = useCallback((data: HistoryListResponse) => {
    setCache((prev) => ({ ...prev, historyData: data }));
  }, []);

  const invalidate = useCallback(() => {
    setCache({ liveData: null, historyData: null });
  }, []);

  return (
    <CacheContext.Provider value={{ ...cache, setLiveData, setHistoryData, invalidate }}>
      {children}
    </CacheContext.Provider>
  );
}

export function useCache(): CacheContextValue {
  const ctx = useContext(CacheContext);
  if (!ctx) throw new Error("useCache must be used within CacheProvider");
  return ctx;
}
