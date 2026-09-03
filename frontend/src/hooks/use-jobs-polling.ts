"use client";

import { startTransition, useCallback, useEffect, useRef, useState } from "react";

import type { JobListItem, JobsList } from "@/lib/types";

async function readJobsList(response: Response): Promise<JobsList> {
  return (await response.json()) as JobsList;
}

/**
 * Poll /api/jobs while any job is active so the table stays current
 * without a full page reload.
 */
export function useJobsPolling(initialJobs: JobListItem[], initialHasActiveJobs: boolean) {
  const [jobs, setJobs] = useState(initialJobs);
  const [hasActiveJobsState, setHasActiveJobsState] = useState(initialHasActiveJobs);
  const [isRefreshingJobs, setIsRefreshingJobs] = useState(false);
  const pollTimerRef = useRef<number | null>(null);
  const isRefreshingRef = useRef(false);

  const refreshJobs = useCallback(async () => {
    if (isRefreshingRef.current) {
      return false;
    }

    isRefreshingRef.current = true;
    setIsRefreshingJobs(true);
    try {
      const response = await fetch("/api/jobs?limit=3", {
        method: "GET",
        headers: {
          accept: "application/json",
        },
        cache: "no-store",
      });

      if (response.status === 404 || response.status === 401 || !response.ok) {
        return false;
      }

      const payload = await readJobsList(response);
      startTransition(() => {
        setJobs(payload.items);
        setHasActiveJobsState(payload.has_active_jobs);
      });
      return true;
    } finally {
      isRefreshingRef.current = false;
      setIsRefreshingJobs(false);
    }
  }, []);

  useEffect(() => {
    if (!hasActiveJobsState) {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    void refreshJobs();
    pollTimerRef.current = window.setInterval(() => {
      void refreshJobs();
    }, 2000);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [hasActiveJobsState, refreshJobs]);

  return {
    jobs,
    setJobs,
    hasActiveJobsState,
    setHasActiveJobsState,
    isRefreshingJobs,
    refreshJobs,
  };
}
