import { redirect } from "next/navigation";

import { BrandMark } from "@/components/brand-mark";
import { fetchBackendJson, getSession } from "@/lib/backend";

type LoginPageProps = {
  searchParams?: Promise<{
    error?: string;
  }>;
};

type LoginContext = {
  has_users: boolean;
  user_count: number;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const session = await getSession();
  if (session) {
    redirect("/app");
  }

  const params = (await searchParams) || {};
  const errorMessage = params.error ? decodeURIComponent(params.error) : null;
  const loginContext = await fetchBackendJson<LoginContext>("/api/v1/auth/login-context");

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="login-brand">
          <div className="brand-badge">
            <BrandMark />
          </div>
          <div>
            <strong>REDCap Batch Locking</strong>
            <span>Internal platform</span>
          </div>
        </div>

        <div className="login-copy">
          <p className="mini-label">Authentication</p>
          <h1 className="login-title">Sign in</h1>
          <p className="section-subtitle">
            Enter your internal account details to access the REDCap batch locking workspace.
          </p>
        </div>

        <form action="/api/session/login" method="post" className="auth-form">
          <label className="field">
            <span>Email</span>
            <input type="email" name="email" autoComplete="email" required />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              minLength={8}
              required
            />
          </label>

          {errorMessage ? <p className="error-message">{errorMessage}</p> : null}

          <button type="submit" className="primary-button">
            Sign in
          </button>
        </form>

        {!loginContext.has_users ? (
          <div className="notice-card">
            <h4>No users found yet</h4>
            <p>
              Bootstrap the first admin account with{" "}
              <code>python scripts/create_superuser.py --email ...</code>.
            </p>
          </div>
        ) : null}

        <div className="login-footer">
          <span>
            Provisioned users: <strong>{loginContext.user_count}</strong>
          </span>
          <span>Audit trail enabled</span>
        </div>
      </section>
    </main>
  );
}
