import { MappingsManager } from "@/components/mappings-manager";
import { fetchBackendJson } from "@/lib/backend";
import type { MappingReviewDetail } from "@/lib/types";

type MappingsPageProps = {
  searchParams?: Promise<{
    error?: string;
    job_id?: string;
    success?: string;
  }>;
};

export default async function MappingsPage({ searchParams }: MappingsPageProps) {
  const params = (await searchParams) || {};
  const query = params.job_id ? `?job_id=${encodeURIComponent(params.job_id)}` : "";
  const review = await fetchBackendJson<MappingReviewDetail>(`/api/v1/mappings/review${query}`);
  const initialBanner = params.success
    ? { tone: "success" as const, message: decodeURIComponent(params.success) }
    : params.error
      ? { tone: "error" as const, message: decodeURIComponent(params.error) }
      : null;

  return <MappingsManager initialBanner={initialBanner} initialReview={review} />;
}
