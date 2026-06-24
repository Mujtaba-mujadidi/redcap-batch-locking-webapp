import type { ReactNode } from "react";

import { WorkspaceShell } from "@/components/workspace-shell";
import { requireSession } from "@/lib/backend";

export default async function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  const session = await requireSession();

  return <WorkspaceShell currentUser={session.user}>{children}</WorkspaceShell>;
}
