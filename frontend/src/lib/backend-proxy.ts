import { NextResponse } from "next/server";

import { backendOrigin } from "@/lib/env";

export async function proxyBackendJsonRequest(
  request: Request,
  path: string,
  method: "POST" | "PATCH",
): Promise<NextResponse> {
  const headers = new Headers({
    accept: "application/json",
  });
  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }

  const contentType = request.headers.get("content-type");
  const rawBody = await request.text();
  if (rawBody) {
    headers.set("content-type", contentType || "application/json");
  }

  const backendResponse = await fetch(new URL(path, backendOrigin), {
    method,
    headers,
    body: rawBody || undefined,
    cache: "no-store",
  });

  const response = new NextResponse(await backendResponse.text(), {
    status: backendResponse.status,
  });
  const responseContentType = backendResponse.headers.get("content-type");
  if (responseContentType) {
    response.headers.set("content-type", responseContentType);
  }

  const setCookie = backendResponse.headers.get("set-cookie");
  if (setCookie) {
    response.headers.set("set-cookie", setCookie);
  }

  return response;
}
