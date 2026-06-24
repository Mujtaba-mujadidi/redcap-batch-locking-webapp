import { proxyBackendJsonRequest } from "@/lib/backend-proxy";

export async function POST(request: Request) {
  return proxyBackendJsonRequest(request, "/api/v1/users", "POST");
}
