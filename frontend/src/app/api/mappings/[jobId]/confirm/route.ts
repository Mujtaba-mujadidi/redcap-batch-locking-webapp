import { proxyBackendFormAction } from "@/lib/backend-proxy";

type RouteContext = {
  params: Promise<{
    jobId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { jobId } = await context.params;
  const formData = await request.formData();
  return proxyBackendFormAction(request, `/mappings/${jobId}/confirm`, formData);
}
