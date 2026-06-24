import { proxyBackendGetRequest } from "@/lib/backend-proxy";

export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyBackendGetRequest(request, `/api/v1/jobs${search}`);
}
