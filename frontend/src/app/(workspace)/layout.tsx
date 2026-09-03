import type { ReactNode } from "react";

import { DesktopExpiredScreen } from "@/components/desktop-expired-screen";
import { DesktopExpiryBanner } from "@/components/desktop-expiry-banner";
import { WorkspaceShell } from "@/components/workspace-shell";
import { fetchBackendJson, requireSession } from "@/lib/backend";

type DesktopStatus = {
  expired: boolean;
  expiry_date: string | null;
};

export default async function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  const status = await fetchBackendJson<DesktopStatus>("/api/v1/desktop/status");
  if (status.expired) {
    return <DesktopExpiredScreen expiryDate={status.expiry_date} />;
  }

  const session = await requireSession();

  return (
    <>
      <DesktopExpiryBanner />
      <WorkspaceShell currentUser={session.user}>{children}</WorkspaceShell>
    </>
  );
}
