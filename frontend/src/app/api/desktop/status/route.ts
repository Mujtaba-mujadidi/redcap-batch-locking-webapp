import { NextResponse } from "next/server";

import { proxyBackendGetRequest } from "@/lib/backend-proxy";

export async function GET(request: Request) {
  return proxyBackendGetRequest(request, "/api/v1/desktop/status");
}
