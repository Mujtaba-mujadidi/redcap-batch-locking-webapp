"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import type { BackendActionResult, MappingReviewDetail } from "@/lib/types";

type BannerState =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

type MappingsManagerProps = {
  initialBanner: BannerState;
  initialReview: MappingReviewDetail;
};

async function readActionResult(response: Response): Promise<BackendActionResult> {
  return (await response.json()) as BackendActionResult;
}

function confidenceTone(confidence: string): string {
  if (confidence === "high") {
    return "status-active";
  }
  if (confidence === "confirm") {
    return "status-review";
  }
  return "status-inactive";
}

function confidenceLabel(confidence: string): string {
  if (confidence === "high") {
    return "High Confidence";
  }
  if (confidence === "confirm") {
    return "Needs Review";
  }
  return "Not Found";
}

export function MappingsManager({
  initialBanner,
  initialReview,
}: MappingsManagerProps) {
  const router = useRouter();
  const [banner, setBanner] = useState<BannerState>(initialBanner);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [review, setReview] = useState(initialReview);

  useEffect(() => {
    setReview(initialReview);
  }, [initialReview]);

  useEffect(() => {
    setBanner(initialBanner);
  }, [initialBanner]);

  async function runAction(
    endpoint: string,
    body: FormData,
    busyLabel: string,
  ): Promise<BackendActionResult | null> {
    setBusyKey(busyLabel);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body,
      });
      const result = await readActionResult(response);
      if (response.status === 401) {
        return null;
      }
      return result;
    } finally {
      setBusyKey(null);
    }
  }

  async function handleRefreshMappings() {
    if (!review.job_id) {
      return;
    }

    const formData = new FormData();
    formData.set("return_to", "mappings");
    const result = await runAction(`/api/mappings/${review.job_id}/refresh`, formData, "refresh");
    if (!result) {
      return;
    }
    setBanner({
      tone: result.ok ? "success" : "error",
      message: result.message || "Mapping refresh finished.",
    });
    router.refresh();
  }

  async function handleUseExistingMappings() {
    if (!review.job_id) {
      return;
    }

    const result = await runAction(
      `/api/jobs/${review.job_id}/use-existing-mappings`,
      new FormData(),
      "use-existing",
    );
    if (!result) {
      return;
    }
    if (!result.ok) {
      setBanner({
        tone: "error",
        message: result.message || "Unable to continue with the saved mappings.",
      });
      return;
    }
    router.push(result.redirect_path || "/jobs");
  }

  async function handleConfirmSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!review.job_id) {
      return;
    }

    const result = await runAction(
      `/api/mappings/${review.job_id}/confirm`,
      new FormData(event.currentTarget),
      "confirm",
    );
    if (!result) {
      return;
    }
    if (!result.ok) {
      setBanner({
        tone: "error",
        message: result.message || "Unable to save those mappings.",
      });
      return;
    }
    router.push(result.redirect_path || "/jobs");
  }

  return (
    <>
      <PageHeader
        eyebrow="Field Mapping"
        title="Mappings"
        description="Review saved mapping context, refresh REDCap metadata when needed, and confirm the fields that should drive lock status and lock date updates."
        actions={
          <>
            {review.job_id && review.job_status === "awaiting_mapping_confirmation" ? (
              <button
                type="button"
                className="header-action"
                onClick={() => void handleRefreshMappings()}
                disabled={busyKey === "refresh"}
              >
                {busyKey === "refresh" ? "Refreshing..." : "Refresh Options"}
              </button>
            ) : null}
            <Link className="primary-button primary-button-inline" href="/jobs">
              Back to Jobs
            </Link>
          </>
        }
      />

      {banner ? (
        <div className={`banner ${banner.tone === "success" ? "banner-success" : "banner-error"}`}>
          {banner.message}
        </div>
      ) : null}

      {!review.job_id ? (
        <section className="panel-card support-note-card">
          <div className="panel-card-header">
            <div>
              <p className="mini-label">Mappings</p>
              <h3>No job is waiting for review</h3>
            </div>
          </div>
          <p className="compact-copy">
            Import a request CSV from the Jobs page to fetch REDCap metadata and prepare a mapping review.
          </p>
        </section>
      ) : review.refresh_decision_pending ? (
        <section className="panel-card support-note-card">
          <div className="panel-card-header">
            <div>
              <p className="mini-label">Refresh Decision</p>
              <h3>Saved mappings already exist for this REDCap project</h3>
            </div>
          </div>
          <p className="compact-copy">
            This project already has saved mappings for {review.confirmed_mapping_count} form
            {review.confirmed_mapping_count === 1 ? "" : "s"}. Decide whether to refresh those mappings from live REDCap metadata or continue with the saved set first.
          </p>
          <div className="modal-actions">
            <button
              type="button"
              className="header-action"
              onClick={() => void handleRefreshMappings()}
              disabled={busyKey === "refresh"}
            >
              {busyKey === "refresh" ? "Refreshing..." : "Refresh Mappings"}
            </button>
            <button
              type="button"
              className="primary-button primary-button-inline"
              onClick={() => void handleUseExistingMappings()}
              disabled={busyKey === "use-existing"}
            >
              {busyKey === "use-existing" ? "Continuing..." : "Use Existing Mappings"}
            </button>
          </div>
        </section>
      ) : (
        <>
          <section className="stats-grid mapping-summary-grid">
            <article className="stat-card">
              <span className="stat-label">Job Status</span>
              <span className="stat-value">{(review.job_status || "unknown").replaceAll("_", " ")}</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Request Rows</span>
              <span className="stat-value">{review.total_rows}</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Forms To Review</span>
              <span className="stat-value">{review.rows.length}</span>
            </article>
          </section>

          {review.rows.length ? (
            <form className="auth-form" onSubmit={handleConfirmSubmit}>
              {review.rows.map((row) => (
                <section key={row.mapping_id} className="panel-card mapping-review-card">
                  <div className="panel-card-header">
                    <div>
                      <p className="mini-label">{row.instrument_name}</p>
                      <h3>{row.instrument_label}</h3>
                      <p className="compact-copy">
                        Form completion always uses <span className="mono">{row.instrument_name}_complete</span>.
                      </p>
                    </div>
                    <span className={`status-pill ${confidenceTone(row.confidence)}`}>
                      {confidenceLabel(row.confidence)}
                    </span>
                  </div>

                  {row.notes.length ? (
                    <div className="notice-card mapping-note-list">
                      {row.notes.map((note) => (
                        <p key={note}>{note}</p>
                      ))}
                    </div>
                  ) : null}

                  <div className="table-shell">
                    <table className="data-table mapping-table">
                      <thead>
                        <tr>
                          <th>Mapping</th>
                          <th>Auto-Detected</th>
                          <th>Select Field</th>
                          <th>Manual Field Name</th>
                          <th>Learn Label Variant</th>
                          <th>Value / Format</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><strong>Lock status field</strong></td>
                          <td>
                            {row.selected_status_candidate ? (
                              <>
                                <span className="mono">{row.selected_status_candidate.field_name}</span>
                                {row.selected_status_candidate.field_label ? (
                                  <p className="compact-copy">{row.selected_status_candidate.field_label}</p>
                                ) : null}
                              </>
                            ) : (
                              <span className="compact-copy">None detected automatically</span>
                            )}
                          </td>
                          <td>
                            <select
                              name={`mapping_${row.mapping_id}_status_field_name`}
                              className="field-select mapping-cell-input"
                              defaultValue={row.selected_status_field_name}
                            >
                              <option value={review.mapping_none_option}>No extra status field</option>
                              {row.status_options.map((option) => (
                                <option key={option.field_name} value={option.field_name}>
                                  {option.field_name}
                                  {option.field_label ? ` — ${option.field_label}` : ""}
                                  {` (${option.field_type})`}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <input
                              name={`mapping_${row.mapping_id}_status_manual_field_name`}
                              type="text"
                              maxLength={255}
                              className="mapping-cell-input"
                            />
                          </td>
                          <td>
                            <input
                              name={`mapping_${row.mapping_id}_status_label_variant`}
                              type="text"
                              maxLength={255}
                              className="mapping-cell-input"
                            />
                          </td>
                          <td>
                            <input
                              name={`mapping_${row.mapping_id}_status_lock_value`}
                              type="text"
                              maxLength={100}
                              defaultValue={row.selected_status_lock_value}
                              className="mapping-cell-input"
                            />
                            {row.selected_status_value_help ? (
                              <p className="mapping-input-help">{row.selected_status_value_help}</p>
                            ) : null}
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Lock date field</strong></td>
                          <td>
                            {row.selected_date_candidate ? (
                              <>
                                <span className="mono">{row.selected_date_candidate.field_name}</span>
                                {row.selected_date_candidate.field_label ? (
                                  <p className="compact-copy">{row.selected_date_candidate.field_label}</p>
                                ) : null}
                              </>
                            ) : (
                              <span className="compact-copy">None detected automatically</span>
                            )}
                          </td>
                          <td>
                            <select
                              name={`mapping_${row.mapping_id}_date_field_name`}
                              className="field-select mapping-cell-input"
                              defaultValue={row.selected_date_field_name}
                            >
                              <option value={review.mapping_none_option}>No extra lock date field</option>
                              {row.date_options.map((option) => (
                                <option key={option.field_name} value={option.field_name}>
                                  {option.field_name}
                                  {option.field_label ? ` — ${option.field_label}` : ""}
                                  {option.validation_type ? ` (${option.validation_type})` : ""}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <input
                              name={`mapping_${row.mapping_id}_date_manual_field_name`}
                              type="text"
                              maxLength={255}
                              className="mapping-cell-input"
                            />
                          </td>
                          <td>
                            <input
                              name={`mapping_${row.mapping_id}_date_label_variant`}
                              type="text"
                              maxLength={255}
                              className="mapping-cell-input"
                            />
                          </td>
                          <td>
                            <select
                              name={`mapping_${row.mapping_id}_date_format`}
                              className="field-select mapping-cell-input"
                              defaultValue={row.selected_date_format}
                            >
                              <option value={review.mapping_auto_option}>Auto detect</option>
                              {review.date_format_options.map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </section>
              ))}

              <div className="mapping-card-footer">
                <button
                  type="submit"
                  className={`primary-button primary-button-inline${busyKey === "confirm" ? " is-busy" : ""}`}
                  disabled={busyKey === "confirm"}
                >
                  {busyKey === "confirm" ? "Saving..." : "Save Mappings"}
                </button>
              </div>
            </form>
          ) : (
            <section className="panel-card support-note-card">
              <div className="panel-card-header">
                <div>
                  <p className="mini-label">Mappings</p>
                  <h3>No forms require manual confirmation</h3>
                </div>
              </div>
              <p className="compact-copy">
                The app found one clear status/date match for each requested form, so this job does not need manual mapping review anymore.
              </p>
            </section>
          )}
        </>
      )}
    </>
  );
}
