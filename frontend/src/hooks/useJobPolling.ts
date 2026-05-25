"use client";

import { useCallback, useEffect, useRef } from "react";
import { fetchJobStatus, fetchJobResult } from "@/lib/api";
import type { JobStatusResponse, AnalyzeResultResponse } from "@/lib/types";

interface UseJobPollingOptions {
  jobId: string;
  onStatusChange?: (status: JobStatusResponse) => void;
  onResult?: (result: AnalyzeResultResponse) => void;
  onError?: (message: string) => void;
  interval?: number;
  timeout?: number;
}

export function useJobPolling({ jobId, onStatusChange, onResult, onError, interval = 3000, timeout = 120000 }: UseJobPollingOptions) {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    intervalRef.current = null;
    timeoutRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const status = await fetchJobStatus(jobId);
        if (cancelled) return;
        onStatusChange?.(status);

        if (status.status === "success") {
          stop();
          try {
            const result = await fetchJobResult(jobId);
            if (!cancelled) onResult?.(result);
          } catch (err) {
            if (!cancelled) onError?.(err instanceof Error ? err.message : "Failed to load result");
          }
        } else if (status.status === "failed" || status.status === "not_found") {
          stop();
          onError?.(status.error || `Job ${status.status}`);
        }
      } catch (err) {
        if (!cancelled) {
          stop();
          onError?.(err instanceof Error ? err.message : "Failed to fetch job status");
        }
      }
    }

    poll();

    if (interval > 0) {
      intervalRef.current = setInterval(poll, interval);
    }

    if (timeout > 0) {
      timeoutRef.current = setTimeout(() => {
        stop();
        onError?.("Job polling timed out");
      }, timeout);
    }

    return () => {
      cancelled = true;
      stop();
    };
  }, [jobId, interval, timeout, onStatusChange, onResult, onError, stop]);

  return { stop };
}
