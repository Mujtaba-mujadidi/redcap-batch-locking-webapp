import { JobsManager } from "@/components/jobs-manager";
import { BackendRequestError, fetchBackendJson } from "@/lib/backend";
import type { JobsList } from "@/lib/types";

type JobsPageProps = {
  searchParams?: Promise<{
    success?: string;
    error?: string;
    import_error?: string;
  }>;
};

const EMPTY_JOBS: JobsList = {
  items: [],
  has_active_jobs: false,
};

export default async function JobsPage({ searchParams }: JobsPageProps) {
  const params = (await searchParams) || {};
  let jobs = EMPTY_JOBS;
  let loadError: string | null = null;

  try {
    jobs = await fetchBackendJson<JobsList>("/api/v1/jobs?limit=3");
  } catch (error) {
    loadError =
      error instanceof BackendRequestError
        ? error.message
        : error instanceof Error
          ? error.message
          : "Could not load jobs from the local API.";
  }

  const initialBanner = params.success
    ? { tone: "success" as const, message: decodeURIComponent(params.success) }
    : params.error
      ? { tone: "error" as const, message: decodeURIComponent(params.error) }
      : params.import_error
        ? { tone: "error" as const, message: decodeURIComponent(params.import_error) }
        : loadError
          ? {
              tone: "error" as const,
              message: `${loadError} Quit other copies of the app if this keeps happening, then reopen.`,
            }
          : null;

  return (
    <JobsManager
      hasActiveJobs={jobs.has_active_jobs}
      initialBanner={initialBanner}
      initialJobs={jobs.items}
    />
  );
}
