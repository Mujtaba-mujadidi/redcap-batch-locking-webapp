import { proxyBackendJsonRequest } from "@/lib/backend-proxy";

type RouteContext = {
  params: Promise<{
    userId: string;
  }>;
};

export async function PATCH(request: Request, context: RouteContext) {
  const { userId } = await context.params;
  return proxyBackendJsonRequest(request, `/api/v1/users/${userId}`, "PATCH");
}
