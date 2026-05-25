"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJobStatus, fetchLiveResults, triggerLiveAnalyze } from "@/lib/api";
import type { LiveResultsResponse } from "@/lib/types";

export function useLiveData() {
  const [data, setData] = useState<LiveResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    pollRef.current = null;
    timeoutRef.current = null;
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetchLiveResults();
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load live IPO data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      if (!cancelled) load().catch(() => {});
    }, 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [load]);

  const refresh = useCallback(async (force: boolean) => {
    clearTimers();
    setRefreshing(true);
    setError(null);
    try {
      const job = await triggerLiveAnalyze(force);
      let done = false;

      const pollJob = async () => {
        try {
          const status = await fetchJobStatus(job.job_id);
          if (status.status === "success") {
            done = true;
            clearTimers();
            await load();
            setRefreshing(false);
            return;
          }
          if (status.status === "failed" || status.status === "not_found") {
            done = true;
            clearTimers();
            setRefreshing(false);
            setError(status.error || `Refresh job ${status.status}`);
          }
        } catch (err) {
          done = true;
          clearTimers();
          setRefreshing(false);
          setError(err instanceof Error ? err.message : "Refresh status check failed");
        }
      };

      await pollJob();
      if (done) return;

      const poll = setInterval(pollJob, 2000);
      pollRef.current = poll;
      const safetyTimeout = setTimeout(() => {
        clearTimers();
        setRefreshing(false);
        load().catch((err) => {
          setError(err instanceof Error ? err.message : "Refresh timed out");
        });
      }, 120000);
      timeoutRef.current = safetyTimeout;
    } catch (err) {
      clearTimers();
      setRefreshing(false);
      setError(err instanceof Error ? err.message : "Refresh failed");
    }
  }, [clearTimers, load]);

  return { data, loading, refreshing, error, refresh, setError, load };
}
