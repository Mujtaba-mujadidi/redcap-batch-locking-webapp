export type CsvDownloadProgress = {
  stage: string;
  percent: number;
};

export type CsvDownloadResult =
  | { ok: true; fileName: string; savedPath?: string }
  | { ok: false; message: string; cancelled?: boolean };

function ensureCsvExtension(path: string): string {
  return /\.csv$/i.test(path) ? path : `${path}.csv`;
}

function parseDownloadFilename(dispositionHeader: string): string {
  if (!dispositionHeader) {
    return "";
  }

  const utf8Match = dispositionHeader.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const quotedMatch = dispositionHeader.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) {
    return quotedMatch[1];
  }

  const plainMatch = dispositionHeader.match(/filename=([^;]+)/i);
  return plainMatch?.[1]?.trim() || "";
}

async function isTauriRuntime(): Promise<boolean> {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const { isTauri } = await import("@tauri-apps/api/core");
    return isTauri();
  } catch {
    return false;
  }
}

async function saveCsvBlob(
  blob: Blob,
  fileName: string,
  dialogTitle: string,
  onProgress?: (progress: CsvDownloadProgress) => void,
): Promise<CsvDownloadResult> {
  onProgress?.({ stage: "Choose where to save the file", percent: 72 });

  if (await isTauriRuntime()) {
    try {
      const [{ save }, { writeTextFile }] = await Promise.all([
        import("@tauri-apps/plugin-dialog"),
        import("@tauri-apps/plugin-fs"),
      ]);

      const savePath = await save({
        defaultPath: fileName,
        title: dialogTitle,
        filters: [{ name: "CSV", extensions: ["csv"] }],
      });

      if (!savePath) {
        return { ok: false, message: "Export cancelled.", cancelled: true };
      }

      const resolvedSavePath = ensureCsvExtension(savePath);
      onProgress?.({ stage: "Writing file", percent: 88 });
      await writeTextFile(resolvedSavePath, await blob.text());
      onProgress?.({ stage: "Export complete", percent: 100 });

      const savedLeafName = resolvedSavePath.split(/[/\\]/).pop() || fileName;
      return { ok: true, fileName: savedLeafName, savedPath: resolvedSavePath };
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      return {
        ok: false,
        message: detail ? `Could not save the file: ${detail}` : "Could not save the file.",
      };
    }
  }

  onProgress?.({ stage: "Starting download", percent: 88 });
  const downloadUrl = window.URL.createObjectURL(blob);
  const downloadLink = document.createElement("a");
  downloadLink.href = downloadUrl;
  downloadLink.download = fileName;
  document.body.appendChild(downloadLink);
  downloadLink.click();
  downloadLink.remove();
  window.setTimeout(() => {
    window.URL.revokeObjectURL(downloadUrl);
  }, 1000);
  onProgress?.({ stage: "Export complete", percent: 100 });
  return { ok: true, fileName };
}

export async function exportReport(
  reportId: string,
  options: {
    onProgress?: (progress: CsvDownloadProgress) => void;
    suggestedFileName?: string;
  } = {},
): Promise<CsvDownloadResult> {
  const { onProgress, suggestedFileName } = options;

  onProgress?.({ stage: "Preparing report export", percent: 12 });

  const response = await fetch(`/api/reports/${reportId}/download`, {
    method: "GET",
    cache: "no-store",
  });

  if (response.status === 401) {
    return { ok: false, message: "Your local session expired. Quit and reopen the app, then retry the export." };
  }

  if (!response.ok) {
    return { ok: false, message: `Export failed with status ${response.status}.` };
  }

  const dispositionHeader = response.headers.get("content-disposition") || "";
  if (!/attachment/i.test(dispositionHeader)) {
    return { ok: false, message: "The server did not return a downloadable report file." };
  }

  onProgress?.({ stage: "Building CSV report", percent: 48 });

  const fileName = parseDownloadFilename(dispositionHeader) || suggestedFileName || "job-report.csv";
  const blob = await response.blob();
  return saveCsvBlob(blob, fileName, "Save report", onProgress);
}

export async function exportRequestTemplate(
  options: {
    onProgress?: (progress: CsvDownloadProgress) => void;
  } = {},
): Promise<CsvDownloadResult> {
  const { onProgress } = options;

  onProgress?.({ stage: "Preparing request template", percent: 20 });

  const response = await fetch("/api/jobs/template", {
    method: "GET",
    cache: "no-store",
  });

  if (response.status === 401) {
    return {
      ok: false,
      message: "Your local session expired. Quit and reopen the app, then retry the export.",
    };
  }

  if (!response.ok) {
    return { ok: false, message: `Template export failed with status ${response.status}.` };
  }

  const dispositionHeader = response.headers.get("content-disposition") || "";
  const fileName =
    parseDownloadFilename(dispositionHeader) || "redcap-batch-request-template.csv";
  const blob = await response.blob();

  // Tauri webviews often render attachment links as plain text; always use save/download helpers.
  return saveCsvBlob(blob, fileName, "Save request template", onProgress);
}

export type ReportExportProgress = CsvDownloadProgress;
export type ReportExportResult = CsvDownloadResult;
