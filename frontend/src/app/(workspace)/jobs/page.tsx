import { JobsManager } from "@/components/jobs-manager";
import { fetchBackendJson } from "@/lib/backend";
import type { JobsList } from "@/lib/types";

type JobsPageProps = {
  searchParams?: Promise<{
    success?: string;
    error?: string;
    import_error?: string;
  }>;
};

export default async function JobsPage({ searchParams }: JobsPageProps) {
  const jobs = await fetchBackendJson<JobsList>("/api/v1/jobs?limit=3");
  const params = (await searchParams) || {};
  const initialBanner = params.success
    ? { tone: "success" as const, message: decodeURIComponent(params.success) }
    : params.error
      ? { tone: "error" as const, message: decodeURIComponent(params.error) }
      : params.import_error
        ? { tone: "error" as const, message: decodeURIComponent(params.import_error) }
        : null;

  return (
    <JobsManager
      hasActiveJobs={jobs.has_active_jobs}
      initialBanner={initialBanner}
      initialJobs={jobs.items}
    />
  );
}
