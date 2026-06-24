"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { formatDate, formatStatus } from "@/lib/format";
import type { BackendActionResult, JobListItem } from "@/lib/types";

type BannerState =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

type JobsManagerProps = {
  hasActiveJobs: boolean;
  initialBanner: BannerState;
  initialJobs: JobListItem[];
};

async function readActionResult(response: Response): Promise<BackendActionResult> {
  return (await response.json()) as BackendActionResult;
}

function processModeLabel(mode: string | null): string {
  return mode === "live" ? "Live in this browser session" : "Background worker";
}

function isTerminalJob(status: string): boolean {
  return ["completed", "cancelled", "failed"].includes(status);
}

function reviewLabel(reviewCount: number): string {
  if (!reviewCount) {
    return "No review required";
  }

  return `${reviewCount} form${reviewCount === 1 ? "" : "s"} to review`;
}

function ModalFrame({
  children,
  isOpen,
  labelledBy,
  onClose,
}: {
  children: ReactNode;
  isOpen: boolean;
  labelledBy: string;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" hidden={!isOpen} onClick={onClose}>
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function JobsManager({
  hasActiveJobs,
  initialBanner,
  initialJobs,
}: JobsManagerProps) {
  const router = useRouter();
  const importFormRef = useRef<HTMLFormElement | null>(null);
  const [jobs, setJobs] = useState(initialJobs);
  const [banner, setBanner] = useState<BannerState>(initialBanner);
  const [importOpen, setImportOpen] = useState(false);
  const [importApiUrl, setImportApiUrl] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [processJob, setProcessJob] = useState<JobListItem | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);
  const visibleJobs = jobs.slice(0, 3);

  useEffect(() => {
    setJobs(initialJobs);
  }, [initialJobs]);

  useEffect(() => {
    setBanner(initialBanner);
  }, [initialBanner]);

  useEffect(() => {
    if (processJob === null) {
      document.body.classList.remove("modal-open");
      return;
    }

    document.body.classList.add("modal-open");

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setProcessJob(null);
        setProcessError(null);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.classList.remove("modal-open");
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [processJob]);

  function closeProcessModal() {
    setProcessJob(null);
    setProcessError(null);
  }

  async function refreshJobs() {
    router.refresh();
  }

  async function runAction(
    endpoint: string,
    body?: FormData,
    busyLabel?: string,
  ): Promise<BackendActionResult | null> {
    setBusyKey(busyLabel || endpoint);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: body || new FormData(),
      });
      const result = await readActionResult(response);
      if (response.status === 401) {
        router.push("/login");
        return null;
      }
      if (!response.ok || !result.ok) {
        return result;
      }
      return result;
    } finally {
      setBusyKey(null);
    }
  }

  async function handleImportSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBanner(null);

    const form = event.currentTarget;
    const result = await runAction("/api/jobs/import", new FormData(form), "import");
    if (!result) {
      return;
    }
    if (!result.ok) {
      setImportOpen(true);
      setBanner({
        tone: "error",
        message: result.message || "Unable to import that request package.",
      });
      setImportApiUrl(result.redirect_query.import_api_url || importApiUrl);
      return;
    }

    setBanner({
      tone: "success",
      message: result.message || "Request imported successfully.",
    });
    setImportOpen(false);
    setImportApiUrl("");
    importFormRef.current?.reset();
    await refreshJobs();
  }

  async function handleProcessSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!processJob) {
      return;
    }

    setBanner(null);
    setProcessError(null);

    const result = await runAction(
      `/api/jobs/${processJob.id}/process`,
      new FormData(event.currentTarget),
      `process-${processJob.id}`,
    );
    if (!result) {
      return;
    }
    if (!result.ok) {
      setProcessError(result.message || "Unable to start processing for this job.");
      return;
    }

    closeProcessModal();
    setBanner({
      tone: "success",
      message: result.message || "Job processing started.",
    });
    await refreshJobs();
  }

  async function handleSimpleAction(
    endpoint: string,
    successFallback: string,
    busyLabel: string,
    body?: FormData,
  ) {
    setBanner(null);
    const result = await runAction(endpoint, body, busyLabel);
    if (!result) {
      return;
    }
    setBanner({
      tone: result.ok ? "success" : "error",
      message: result.message || successFallback,
    });
    await refreshJobs();
  }

  return (
    <>
      <PageHeader
        eyebrow="Job Queue"
        title="Jobs"
        description="Track the three most recent requests, re-run imports, and move into mapping or processing from one organised workspace."
        actions={
          <>
            <a className="header-action" href="/api/jobs/template">
              Export Template
            </a>
            <button
              className="primary-button primary-button-inline"
              type="button"
              aria-expanded={importOpen}
              onClick={() => setImportOpen((currentValue) => !currentValue)}
            >
              {importOpen ? "Cancel" : "Import File"}
            </button>
          </>
        }
      />

      {importOpen ? (
        <section className="panel-card import-request-card">
          <div className="panel-card-header import-request-header">
            <div>
              <p className="mini-label">Import Request</p>
              <h3>Import a completed request CSV</h3>
              <p className="compact-copy">
                Add the REDCap connection details, upload the request package, and run the same pre-flight checks directly from this page.
              </p>
            </div>
          </div>

          <div className="modal-note import-request-note">
            The API key is cached for this session so repeat processing on the same REDCap host does not always require re-entry.
          </div>

          <form
            ref={importFormRef}
            className="auth-form import-request-form"
            onSubmit={handleImportSubmit}
          >
            <div className="import-request-grid">
              <label className="field">
                <span>API URL</span>
                <input
                  name="redcap_api_url"
                  type="url"
                  autoComplete="off"
                  required
                  value={importApiUrl}
                  onChange={(event) => setImportApiUrl(event.target.value)}
                />
              </label>

              <label className="field">
                <span>API Key</span>
                <input
                  name="redcap_api_key"
                  type="password"
                  autoComplete="new-password"
                  required
                />
              </label>

              <label className="field">
                <span>Request CSV</span>
                <input name="request_file" type="file" accept=".csv,text/csv" required />
                <span className="field-hint">Required. Upload the completed batch request template.</span>
              </label>

              <label className="field">
                <span>Existing Queries Export</span>
                <input name="queries_file" type="file" accept=".csv,text/csv" />
                <span className="field-hint">Optional. Include this when unresolved queries should block lock actions.</span>
              </label>
            </div>

            <div className="modal-actions import-request-actions">
              <button
                type="button"
                className="header-action"
                onClick={() => setImportOpen(false)}
                disabled={busyKey === "import"}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={`primary-button primary-button-inline${busyKey === "import" ? " is-busy" : ""}`}
                disabled={busyKey === "import"}
              >
                {busyKey === "import" ? "Running Import..." : "Run Import"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {banner ? (
        <div className={`banner ${banner.tone === "success" ? "banner-success" : "banner-error"}`}>
          {banner.message}
        </div>
      ) : null}

      <section className="panel-card data-table-card">
        <div className="panel-card-header jobs-panel-header">
          <div>
            <p className="mini-label">Recent Activity</p>
            <h3>Last 3 requests</h3>
            <p className="compact-copy">
              This page stays focused on the latest work. Older generated exports continue to live in the Reports tab.
            </p>
          </div>
        </div>

        {hasActiveJobs ? (
          <div className="banner banner-success queue-banner">
            At least one request is active right now. Use the refresh button in your browser or revisit this page to watch the queue update.
          </div>
        ) : null}

        {visibleJobs.length ? (
          <div className="table-shell">
            <table className="data-table jobs-review-table">
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Results</th>
                  <th>Updated</th>
                  <th className="actions-column">Action</th>
                </tr>
              </thead>
              <tbody>
                {visibleJobs.map((job) => {
                  const terminalJob = isTerminalJob(job.status);
                  const showProgressPanel =
                    Boolean(job.progress.summary) ||
                    Boolean(job.progress.message) ||
                    Boolean(job.progress.detail) ||
                    Boolean(job.progress.wait_message);

                  return (
                    <tr key={job.id}>
                      <td>
                        <div className="job-request-cell">
                          <strong className="job-request-name">
                            {job.request_file_name || "Imported request"}
                          </strong>
                          <p className="compact-copy">
                            {job.project_title || "Untitled project"}
                            {job.project_id ? ` · Project ${job.project_id}` : ""}
                          </p>
                          <div className="job-request-badges">
                            {job.host_label ? (
                              <span className="job-info-pill">{job.host_label}</span>
                            ) : null}
                            <span className="job-info-pill">
                              {job.progress.rate_limit_per_minute} calls/min
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="job-status-cell">
                        <StatusPill status={job.status} label={job.status_label} toneClassName={job.status_tone} />
                        {job.action_hint ? <p className="compact-copy">{job.action_hint}</p> : null}
                      </td>
                      <td>
                        {showProgressPanel ? (
                          <div className="job-progress-panel">
                            <div className="job-progress-header">
                              <div className="job-progress-summary">
                                <strong>{job.progress.summary}</strong>
                                <span
                                  className="loader-spinner loader-spinner-small"
                                  hidden={
                                    ![
                                      "queued",
                                      "running",
                                      "waiting_due_to_rate_limit",
                                      "cancel_requested",
                                    ].includes(job.status)
                                  }
                                  aria-hidden="true"
                                ></span>
                              </div>
                              {!terminalJob ? (
                                <span className="compact-copy">{job.progress.percent}%</span>
                              ) : null}
                            </div>
                            {!terminalJob ? (
                              <div className="job-progress-track" aria-hidden="true">
                                <div
                                  className="job-progress-fill"
                                  style={{ width: `${job.progress.percent}%` }}
                                ></div>
                              </div>
                            ) : null}
                            {job.progress.message ? <p className="compact-copy">{job.progress.message}</p> : null}
                            {job.progress.wait_message ? (
                              <p className="compact-copy job-progress-wait">{job.progress.wait_message}</p>
                            ) : null}
                            {job.progress.detail ? <p className="compact-copy">{job.progress.detail}</p> : null}
                          </div>
                        ) : (
                          <p className="compact-copy">No live progress to show.</p>
                        )}
                      </td>
                      <td>
                        <div className="job-results-cell">
                          <strong className="job-results-total">{job.total_rows} rows</strong>
                          <div className="job-result-stats">
                            <span className="job-result-stat">{job.locked_rows} locked</span>
                            <span className="job-result-stat">{job.unlocked_rows} unlocked</span>
                            <span className="job-result-stat">{job.failed_rows} failed</span>
                          </div>
                          <p className="compact-copy">{reviewLabel(job.review_count)}</p>
                        </div>
                      </td>
                      <td className="job-updated-cell">{formatDate(job.updated_at)}</td>
                      <td className="actions-column job-actions-cell">
                        <div className="table-actions">
                          {job.action_kind || job.cancel_label || job.continue_label || job.remap_label || job.report_id ? (
                            <details className="job-action-menu">
                              <summary className="manage-button">Action</summary>
                              <div className="job-action-menu-list">
                                {job.action_kind === "process" || job.action_kind === "process_cached" ? (
                                  <button
                                    type="button"
                                    className="job-action-menu-button"
                                    onClick={() => {
                                      setProcessError(null);
                                      setProcessJob(job);
                                    }}
                                  >
                                    {job.action_label || "Process"}
                                  </button>
                                ) : null}

                                {job.action_kind === "link" ? (
                                  <Link className="job-action-menu-link" href={`/mappings?job_id=${job.id}`}>
                                    {job.action_label || "Review mappings"}
                                  </Link>
                                ) : null}

                                {job.action_kind === "download" && job.report_id ? (
                                  <a className="job-action-menu-link" href={`/api/reports/${job.report_id}/download`}>
                                    {job.action_label || "Export Report"}
                                  </a>
                                ) : null}

                                {job.remap_label ? (
                                  <button
                                    type="button"
                                    className="job-action-menu-button"
                                    onClick={() => {
                                      const formData = new FormData();
                                      formData.set("return_to", "jobs");
                                      void handleSimpleAction(
                                        `/api/mappings/${job.id}/refresh`,
                                        "Mappings refreshed.",
                                        `refresh-${job.id}`,
                                        formData,
                                      );
                                    }}
                                  >
                                    {job.remap_label}
                                  </button>
                                ) : null}

                                {job.continue_label ? (
                                  <button
                                    type="button"
                                    className="job-action-menu-button"
                                    onClick={() => {
                                      void handleSimpleAction(
                                        `/api/jobs/${job.id}/use-existing-mappings`,
                                        "Saved mappings reused.",
                                        `continue-${job.id}`,
                                      );
                                    }}
                                  >
                                    {job.continue_label}
                                  </button>
                                ) : null}

                                {job.cancel_label ? (
                                  <button
                                    type="button"
                                    className="job-action-menu-button"
                                    onClick={() => {
                                      void handleSimpleAction(
                                        `/api/jobs/${job.id}/cancel`,
                                        "Cancellation requested.",
                                        `cancel-${job.id}`,
                                      );
                                    }}
                                  >
                                    {job.cancel_label}
                                  </button>
                                ) : null}

                                {job.report_id && job.action_kind !== "download" ? (
                                  <a className="job-action-menu-link" href={`/api/reports/${job.report_id}/download`}>
                                    Export Report
                                  </a>
                                ) : null}
                              </div>
                            </details>
                          ) : (
                            <span className="compact-copy">No actions</span>
                          )}

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
          <p className="compact-copy jobs-empty-state">No imported jobs are waiting for review or processing yet.</p>
        )}
      </section>

      <ModalFrame
        isOpen={processJob !== null}
        labelledBy="process-job-modal-title"
        onClose={closeProcessModal}
      >
        <div className="modal-header">
          <div>
            <p className="mini-label">Process Job</p>
            <h3 id="process-job-modal-title">Start selected request</h3>
            <p className="compact-copy">
              {processJob ? `${processJob.request_file_name || "Imported request"} · ${processModeLabel(processJob.launch_mode)}` : "Enter the REDCap API key to start execution."}
            </p>
          </div>
          <button type="button" className="modal-close" aria-label="Close" onClick={closeProcessModal}>
            ×
          </button>
        </div>

        {processJob ? (
          <form className="modal-body auth-form" onSubmit={handleProcessSubmit}>
            <label className="field">
              <span>REDCap API Key</span>
              <input name="redcap_api_key" type="password" autoComplete="new-password" />
            </label>
            <p className="field-hint">
              {processJob.action_kind === "process_cached"
                ? "Leave this blank to reuse the saved session key for this REDCap host, or enter a new key to replace it."
                : "Enter the REDCap API key to begin processing. The key will be cached only for this session."}
            </p>

            {processError ? <p className="error-message">{processError}</p> : null}

            <div className="modal-actions">
              <button type="button" className="header-action" onClick={closeProcessModal}>
                Cancel
              </button>
              <button
                type="submit"
                className={`primary-button primary-button-inline${busyKey === `process-${processJob.id}` ? " is-busy" : ""}`}
                disabled={busyKey === `process-${processJob.id}`}
              >
                {busyKey === `process-${processJob.id}` ? "Starting..." : processJob.action_label || "Process"}
              </button>
            </div>
          </form>
        ) : null}
      </ModalFrame>
    </>
  );
}
