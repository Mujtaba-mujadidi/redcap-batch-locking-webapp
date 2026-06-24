import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { buildLegacyUrl, fetchBackendJson } from "@/lib/backend";
import { formatDate, formatStatus } from "@/lib/format";
import type { JobsList } from "@/lib/types";

export default async function JobsPage() {
  const jobs = await fetchBackendJson<JobsList>("/api/v1/jobs?limit=25");

  return (
    <>
      <PageHeader
        eyebrow="Job Queue"
        title="Jobs"
        description="Review the latest requests, see status changes, and continue into detailed processing where needed."
        actions={
          <>
            <a className="header-action" href={buildLegacyUrl("/jobs/template.csv")}>Export Template</a>
            <a className="primary-button primary-button-inline" href={buildLegacyUrl("/jobs")}>Import File</a>
          </>
        }
      />

      <section className="panel-card data-table-card">
        <div className="panel-card-header">
          <div>
            <p className="mini-label">Job Queue</p>
            <h3>Latest 25 requests</h3>
            <p className="compact-copy">Completed exports remain available from the Reports tab.</p>
          </div>
        </div>

        {jobs.items.length ? (
          <div className="table-shell">
            <table className="data-table jobs-review-table">
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Forms Requiring Review</th>
                  <th>Updated</th>
                  <th className="actions-column">Action</th>
                </tr>
              </thead>
              <tbody>
                {jobs.items.map((job) => {
                  const primaryActionHref =
                    job.report_id && (job.status === "completed" || job.status === "completed_with_errors" || job.status === "failed" || job.status === "cancelled")
                      ? buildLegacyUrl(`/reports/${job.report_id}/download`)
                      : job.review_count > 0
                        ? `/mappings`
                        : buildLegacyUrl("/jobs");

                  const primaryActionLabel =
                    job.report_id && (job.status === "completed" || job.status === "completed_with_errors" || job.status === "failed" || job.status === "cancelled")
                      ? "Export Report"
                      : job.review_count > 0
                        ? "Review mappings"
                        : "Continue";

                  return (
                    <tr key={job.id}>
                      <td>
                        <strong>{job.request_file_name || "Imported request"}</strong>
                        <p className="compact-copy">
                          {job.project_title || "Untitled project"}
                          {job.project_id ? ` · Project ${job.project_id}` : ""}
                        </p>
                        <p className="compact-copy">{job.host_label}</p>
                        <p className="compact-copy">
                          {job.progress.rate_limit_per_minute} calls/min configured for this REDCap project.
                        </p>
                        <p className="compact-copy">
                          {job.progress.message || job.progress.summary}
                        </p>
                      </td>
                      <td>
                        <StatusPill status={job.status} />
                      </td>
                      <td>
                        <strong>{job.total_rows}</strong>
                        <div className="job-result-stats">
                          <span className="job-result-stat">{job.locked_rows} locked</span>
                          <span className="job-result-stat">{job.unlocked_rows} unlocked</span>
                          <span className="job-result-stat">{job.failed_rows} failed</span>
                        </div>
                      </td>
                      <td>
                        {job.review_count ? (
                          `${job.review_count} form${job.review_count === 1 ? "" : "s"}`
                        ) : (
                          <span className="compact-copy">None</span>
                        )}
                      </td>
                      <td>{formatDate(job.updated_at)}</td>
                      <td className="actions-column">
                        <div className="table-actions">
                          <a className="manage-button" href={primaryActionHref}>
                            {primaryActionLabel}
                          </a>
                          {job.status !== "completed" && job.status !== "cancelled" ? (
                            <span className="table-note">{formatStatus(job.job_type)}</span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            No imported requests are visible yet.
          </div>
        )}
      </section>
    </>
  );
}
