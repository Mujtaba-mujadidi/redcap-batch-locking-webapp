import { ReportsManager } from "@/components/reports-manager";
import { BackendRequestError, fetchBackendJson } from "@/lib/backend";
import type { ReportsList } from "@/lib/types";

const EMPTY_REPORTS: ReportsList = {
  items: [],
};

export default async function ReportsPage() {
  let reports = EMPTY_REPORTS;
  let loadError: string | null = null;

  try {
    reports = await fetchBackendJson<ReportsList>("/api/v1/reports");
  } catch (error) {
    loadError =
      error instanceof BackendRequestError
        ? error.message
        : error instanceof Error
          ? error.message
          : "Could not load reports from the local API.";
  }

  return (
    <>
      {loadError ? (
        <div className="banner banner-error">
          {loadError} Quit other copies of the app if this keeps happening, then reopen.
        </div>
      ) : null}
      <ReportsManager initialReports={reports} />
    </>
  );
}
