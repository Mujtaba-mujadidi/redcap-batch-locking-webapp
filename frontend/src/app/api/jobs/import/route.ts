import { proxyBackendFormAction } from "@/lib/backend-proxy";

export async function POST(request: Request) {
  const formData = await request.formData();
  return proxyBackendFormAction(request, "/jobs/import", formData);
}
