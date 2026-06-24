import { PageHeader } from "@/components/page-header";
import { buildLegacyUrl, fetchBackendJson } from "@/lib/backend";
import { formatStatus } from "@/lib/format";
import type { MappingReview } from "@/lib/types";

export default async function MappingsPage() {
  const review = await fetchBackendJson<MappingReview>("/api/v1/mappings/current");

  return (
    <>
      <PageHeader
        eyebrow="Field Mapping"
        title="Mappings"
        description="Review saved mapping context and the current REDCap forms that still need confirmation."
        actions={
          <a className="header-action" href={buildLegacyUrl("/mappings")}>
            Open detailed review
          </a>
        }
      />

      {review.job_id ? (
        <>
          {review.refresh_decision_pending ? (
            <p className="banner banner-error">
              A refresh decision is still pending for {review.confirmed_mapping_count} previously saved mappings in this project.
            </p>
          ) : null}

          <div className="dashboard-panels">
            <article className="panel-card">
              <div className="panel-card-header">
                <div>
                  <p className="mini-label">Project Context</p>
                  <h3>Current review</h3>
                </div>
              </div>
              <h2>Project context</h2>
              <p className="compact-copy">Project: {review.project_title || review.project_id || "Unknown project"}</p>
              <p className="compact-copy">Host: {review.host_label || "Unknown host"}</p>
              <p className="compact-copy">Forms needing confirmation: {review.rows.length}</p>
            </article>
            <article className="panel-card">
              <div className="panel-card-header">
                <div>
                  <p className="mini-label">Saved Mappings</p>
                  <h3>Review notes</h3>
                </div>
              </div>
              <p className="compact-copy">
                Suggested fields are surfaced here from the backend read model so the new frontend keeps the same review workflow vocabulary.
              </p>
            </article>
          </div>

          <section className="panel-card data-table-card">
            <div className="panel-card-header">
              <div>
                <p className="mini-label">Review Queue</p>
                <h3>Forms requiring confirmation</h3>
              </div>
            </div>
            <div className="table-shell">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Instrument</th>
                    <th>Current mapping</th>
                    <th>Suggested fields</th>
                  </tr>
                </thead>
                <tbody>
                  {review.rows.map((row) => (
                    <tr key={row.instrument_name}>
                      <td>
                        <strong>{row.instrument_label || row.instrument_name}</strong>
                        <p className="compact-copy">{formatStatus(row.confidence || "confirm")}</p>
                      </td>
                      <td>
                        <strong>{row.status_field_name || "No status field saved"}</strong>
                        <p className="compact-copy">
                          Complete: {row.form_complete_field_name || "Not set"} · Date: {row.lock_date_field_name || "Not set"}
                        </p>
                      </td>
                      <td>
                        <strong>{row.suggested_status_field_name || "No suggestion"}</strong>
                        <p className="compact-copy">
                          Date: {row.suggested_date_field_name || "No suggestion"} · Lock value: {row.suggested_status_lock_value || "N/A"}
                        </p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <div className="empty-state">
          No mapping review is waiting right now.
        </div>
      )}
    </>
  );
}
