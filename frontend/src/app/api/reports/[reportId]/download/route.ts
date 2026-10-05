import { proxyBackendDownload } from "@/lib/backend-proxy";

type RouteContext = {
  params: Promise<{
    reportId: string;
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { reportId } = await context.params;
  return proxyBackendDownload(request, `/reports/${reportId}/download`);
}
