import { proxyBackendDownload } from "@/lib/backend-proxy";

export async function GET(request: Request) {
  return proxyBackendDownload(request, "/jobs/template.csv");
}
