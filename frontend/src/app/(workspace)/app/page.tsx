import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { buildLegacyUrl, fetchBackendJson } from "@/lib/backend";
import type { WorkspaceSummary } from "@/lib/types";

export default async function OverviewPage() {
  const summary = await fetchBackendJson<WorkspaceSummary>("/api/v1/workspace/summary");

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Operations Dashboard"
        description="Live overview of access, readiness, and the authenticated foundation for the batch locking platform."
        actions={
          <a className="header-action" href={buildLegacyUrl("/app")}>
            Refresh
          </a>
        }
      />

      <div className="tab-row">
        <button className="tab-chip is-active" type="button">
          Overview
        </button>
        <button className="tab-chip" type="button" disabled>
          Session Details
        </button>
      </div>

      <section className="stats-grid stats-grid-wide">
        <MetricCard label="Users" value={summary.stats.users} />
        <MetricCard label="Super Admins" value={summary.stats.super_admins} />
        <MetricCard label="Active Sessions" value={summary.stats.active_sessions} />
        <MetricCard label="Jobs" value={summary.stats.jobs} />
        <MetricCard label="Reports" value={summary.stats.reports} />
        <MetricCard label="Mappings" value={summary.stats.mappings} />
      </section>

      <section className="dashboard-panels">
        <article className="panel-card">
          <div className="panel-card-header">
            <div>
              <p className="mini-label">Workspace Readiness</p>
              <h3>Authentication foundation</h3>
            </div>
          </div>

          <div className="bar-strip">
            <div className="bar-item"><span></span><small>Sessions</small></div>
            <div className="bar-item"><span></span><small>Users</small></div>
            <div className="bar-item"><span></span><small>Roles</small></div>
            <div className="bar-item"><span></span><small>Audit</small></div>
            <div className="bar-item"><span></span><small>Reports</small></div>
            <div className="bar-item"><span></span><small>Jobs</small></div>
            <div className="bar-item"><span></span><small>Mappings</small></div>
          </div>

          <p className="panel-footer-copy">
            Authentication, session storage, audit logging, and the separated frontend shell are now active together.
          </p>
        </article>

        <article className="panel-card">
          <div className="panel-card-header">
            <div>
              <p className="mini-label">Current Account</p>
              <h3>Signed-in user profile</h3>
            </div>
          </div>

          <dl className="detail-list">
            <div>
              <dt>Name</dt>
              <dd>{summary.current_user.full_name || "Not provided"}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{summary.current_user.email}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{summary.current_user.role}</dd>
            </div>
            <div>
              <dt>Manage Users</dt>
              <dd>{summary.permissions.can_manage_users ? "Enabled" : "Not available"}</dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="dashboard-panels dashboard-panels-bottom">
        <article className="panel-card compact-panel">
          <div className="panel-card-header">
            <div>
              <p className="mini-label">Audit</p>
              <h3>Recorded events</h3>
            </div>
          </div>
          <p className="compact-value">{summary.stats.audit_events}</p>
          <p className="compact-copy">
            Audit entries are already being captured for authentication and account activity.
          </p>
        </article>

        <article className="panel-card compact-panel">
          <div className="panel-card-header">
            <div>
              <p className="mini-label">Platform Direction</p>
              <h3>Frontend migration</h3>
            </div>
          </div>
          <p className="compact-copy">
            This workspace now runs from Next.js while reading typed backend responses, which lets us continue
            migrating job execution and user actions without redesigning the product.
          </p>
        </article>
      </section>
    </>
  );
}
