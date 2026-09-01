import type { ReactNode } from "react";

type DesktopExpiredScreenProps = {
  expiryDate: string | null;
  children?: ReactNode;
};

export function DesktopExpiredScreen({ expiryDate }: DesktopExpiredScreenProps) {
  return (
    <main className="login-shell">
      <section className="login-card">
        <h1 className="login-title">Update required</h1>
        <p className="section-subtitle">
          This desktop app version expired
          {expiryDate ? ` on ${expiryDate}` : ""}. Install the latest release to continue using
          REDCap Batch Locking.
        </p>
      </section>
    </main>
  );
}
