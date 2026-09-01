"use client";

import { useCallback, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { ReportExportOverlay } from "@/components/report-export-overlay";
import { StatusPill } from "@/components/status-pill";
import { TableActionMenu } from "@/components/table-action-menu";
import { suggestedReportFileName, useReportExport } from "@/hooks/use-report-export";
import { formatDate } from "@/lib/format";
import type { ReportsList } from "@/lib/types";

type ReportsManagerProps = {
  initialReports: ReportsList;
};

type BannerState =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

function formatByteSize(value: number | null): string {
  if (value === null) {
    return "Pending";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function ReportsManager({ initialReports }: ReportsManagerProps) {
  const [banner, setBanner] = useState<BannerState>(null);
  const handleExportCompleted = useCallback((message: string, tone: "success" | "error") => {
    setBanner({ message, tone });
  }, []);
  const { isExporting, progress, startExport } = useReportExport(handleExportCompleted);

  return (
    <>
      <PageHeader
        eyebrow="Exports"
        title="Reports"
        description="Download generated execution reports as CSV files."
      />

      {banner ? (
        <div className={`banner ${banner.tone === "success" ? "banner-success" : "banner-error"}`}>
          {banner.message}
        </div>
      ) : null}

      <section className="panel-card data-table-card reports-table-card">
        <div className="panel-card-header">
          <div>
            <p className="mini-label">Generated Exports</p>
            <h3>Available report files</h3>
          </div>
        </div>
        {initialReports.items.length ? (
          <div className="table-shell reports-table-shell">
            <table className="data-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Job status</th>
                  <th>Project</th>
                  <th>Size</th>
                  <th>Updated</th>
                  <th className="actions-column">Action</th>
                </tr>
              </thead>
              <tbody>
                {initialReports.items.map((report) => (
                  <tr key={report.report_id}>
                    <td>
                      <strong>{report.file_name}</strong>
                      <p className="compact-copy">{report.request_file_name || "Generated report"}</p>
                    </td>
                    <td>
                      <StatusPill status={report.job_status} />
                    </td>
                    <td>
                      <strong>{report.project_title || report.project_id || "Untitled project"}</strong>
                      <p className="compact-copy">{report.host_label}</p>
                    </td>
                    <td>{formatByteSize(report.byte_size)}</td>
                    <td>{formatDate(report.updated_at)}</td>
                    <td className="actions-column">
                      <TableActionMenu ariaLabel={`Open actions for ${report.file_name}`}>
                        <button
                          type="button"
                          className="table-action-menu-button"
                          disabled={isExporting}
                          onClick={() =>
                            void startExport(
                              report.report_id,
                              suggestedReportFileName(report.request_file_name),
                            )
                          }
                        >
                          {isExporting ? "Exporting..." : "Export"}
                        </button>
                      </TableActionMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">No reports are available yet.</div>
        )}
      </section>

      <ReportExportOverlay
        isOpen={isExporting}
        title={progress.title}
        copy={progress.copy}
        stage={progress.stage}
        percent={progress.percent}
      />
    </>
  );
}
