"use client";

import { useEffect, useState } from "react";

type DesktopStatus = {
  expired: boolean;
  expiry_date: string | null;
  days_remaining: number | null;
  version: string;
};

export function DesktopExpiryBanner() {
  const [status, setStatus] = useState<DesktopStatus | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadStatus() {
      try {
        const response = await fetch("/api/desktop/status");
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as DesktopStatus;
        if (!cancelled) {
          setStatus(payload);
        }
      } catch {
        // Ignore transient status fetch errors in the banner.
      }
    }

    void loadStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === null || status.expired || status.days_remaining === null) {
    return null;
  }

  if (status.days_remaining > 30) {
    return null;
  }

  return (
    <div className="desktop-expiry-banner" role="status">
      Desktop app support ends on {status.expiry_date}. {status.days_remaining} day
      {status.days_remaining === 1 ? "" : "s"} remaining — install an update before then.
    </div>
  );
}
