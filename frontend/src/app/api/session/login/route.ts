import { NextResponse } from "next/server";

import { backendOrigin } from "@/lib/env";
import { createRedirectResponse } from "@/lib/redirect-response";

async function readCredentials(request: Request) {
  const contentType = request.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    const body = (await request.json()) as { email?: string; password?: string };
    return {
      email: String(body.email || "").trim(),
      password: String(body.password || ""),
    };
  }

  const formData = await request.formData();
  return {
    email: String(formData.get("email") || "").trim(),
    password: String(formData.get("password") || ""),
  };
}

export async function POST(request: Request) {
  const { email, password } = await readCredentials(request);

  const backendResponse = await fetch(new URL("/api/v1/auth/login", backendOrigin), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json",
    },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });

  if (!backendResponse.ok) {
    let errorMessage = "Unable to sign in.";
    try {
      const body = (await backendResponse.json()) as { detail?: string };
      errorMessage = body.detail || errorMessage;
    } catch {}

    return createRedirectResponse(`/login?error=${encodeURIComponent(errorMessage)}`);
  }

  const response = createRedirectResponse("/app");
  const setCookie = backendResponse.headers.get("set-cookie");
  if (setCookie) {
    response.headers.set("set-cookie", setCookie);
  }
  return response;
}
