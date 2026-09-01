"use client";

import { useCallback, useEffect, useState } from "react";

import { exportReport, type ReportExportProgress } from "@/lib/report-export";

type ExportBannerHandler = (message: string, tone: "success" | "error") => void;

const initialProgress = {
  title: "Preparing report export",
  copy: "Building the latest CSV report. You will be asked where to save it.",
  stage: "Loading report rows",
  percent: 12,
};

export function useReportExport(onCompleted?: ExportBannerHandler) {
  const [isExporting, setIsExporting] = useState(false);
  const [progress, setProgress] = useState(initialProgress);

  useEffect(() => {
    document.body.classList.toggle("modal-open", isExporting);
    return () => {
      document.body.classList.remove("modal-open");
    };
  }, [isExporting]);

  const startExport = useCallback(
    async (reportId: string, suggestedFileName?: string) => {
      if (isExporting) {
        return;
      }

      setIsExporting(true);
      setProgress(initialProgress);

      try {
        const result = await exportReport(reportId, {
          suggestedFileName,
          onProgress: (nextProgress: ReportExportProgress) => {
            setProgress((current) => ({
              ...current,
              stage: nextProgress.stage,
              percent: nextProgress.percent,
            }));
          },
        });

        if (!result.ok) {
          if (!result.cancelled) {
            onCompleted?.(result.message, "error");
          }
          return;
        }

        onCompleted?.(
          result.savedPath
            ? `Report saved to ${result.savedPath}.`
            : `Report downloaded as ${result.fileName}.`,
          "success",
        );
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Report export failed unexpectedly.";
        onCompleted?.(message, "error");
      } finally {
        setIsExporting(false);
      }
    },
    [isExporting, onCompleted],
  );

  return {
    isExporting,
    progress,
    startExport,
  };
}

export function suggestedReportFileName(
  requestFileName: string | null | undefined,
): string | undefined {
  if (!requestFileName) {
    return undefined;
  }

  const stem = requestFileName.replace(/\.[^.]+$/, "").trim() || "job-report";
  return `${stem}-report.csv`;
}
