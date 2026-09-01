export type ReportExportProgress = {
  stage: string;
  percent: number;
};

export type ReportExportResult =
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

export async function exportReport(
  reportId: string,
  options: {
    onProgress?: (progress: ReportExportProgress) => void;
    suggestedFileName?: string;
  } = {},
): Promise<ReportExportResult> {
  const { onProgress, suggestedFileName } = options;

  onProgress?.({ stage: "Preparing report export", percent: 12 });

  const response = await fetch(`/api/reports/${reportId}/download`, {
    method: "GET",
    cache: "no-store",
  });

  if (response.status === 401) {
    return { ok: false, message: "Your session expired. Sign in again and retry the export." };
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

  onProgress?.({ stage: "Choose where to save the report", percent: 72 });

  if (await isTauriRuntime()) {
    try {
      const [{ save }, { writeTextFile }] = await Promise.all([
        import("@tauri-apps/plugin-dialog"),
        import("@tauri-apps/plugin-fs"),
      ]);

      const savePath = await save({
        defaultPath: fileName,
        title: "Save report",
        filters: [{ name: "CSV report", extensions: ["csv"] }],
      });

      if (!savePath) {
        return { ok: false, message: "Export cancelled.", cancelled: true };
      }

      const resolvedSavePath = ensureCsvExtension(savePath);

      onProgress?.({ stage: "Writing report file", percent: 88 });
      await writeTextFile(resolvedSavePath, await blob.text());

      onProgress?.({ stage: "Export complete", percent: 100 });

      const savedLeafName = resolvedSavePath.split(/[/\\]/).pop() || fileName;
      return { ok: true, fileName: savedLeafName, savedPath: resolvedSavePath };
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      const message = detail
        ? `Could not save the report file: ${detail}`
        : "Could not save the report file.";
      return { ok: false, message };
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
