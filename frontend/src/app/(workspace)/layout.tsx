import type { ReactNode } from "react";

import { DesktopExpiredScreen } from "@/components/desktop-expired-screen";
import { DesktopExpiryBanner } from "@/components/desktop-expiry-banner";
import { WorkspaceShell } from "@/components/workspace-shell";
import { BackendRequestError, fetchBackendJson, requireSession } from "@/lib/backend";

export const dynamic = "force-dynamic";

type DesktopStatus = {
  expired: boolean;
  expiry_date: string | null;
};

function BackendUnavailableScreen({ message }: { message: string }) {
  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="mini-label">Local services</p>
        <h1>Starting REDCap Batch Locking</h1>
        <p className="compact-copy">
          The app could not reach its local API yet. Quit any other open copies of the app, wait a
          moment, then reopen.
        </p>
        <p className="error-message">{message}</p>
      </section>
    </main>
  );
}

export default async function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  let status: DesktopStatus;
  try {
    status = await fetchBackendJson<DesktopStatus>("/api/v1/desktop/status");
  } catch (error) {
    const message =
      error instanceof BackendRequestError
        ? error.message
        : error instanceof Error
          ? error.message
          : "Local API is unavailable.";
    return <BackendUnavailableScreen message={message} />;
  }

  if (status.expired) {
    return <DesktopExpiredScreen expiryDate={status.expiry_date} />;
  }

  let session;
  try {
    session = await requireSession();
  } catch (error) {
    const message =
      error instanceof BackendRequestError
        ? error.message
        : error instanceof Error
          ? error.message
          : "Desktop session is unavailable.";
    return <BackendUnavailableScreen message={message} />;
  }

  return (
    <>
      <DesktopExpiryBanner />
      <WorkspaceShell currentUser={session.user}>{children}</WorkspaceShell>
    </>
  );
}
