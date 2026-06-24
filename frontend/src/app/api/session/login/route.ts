import { NextResponse } from "next/server";

import { backendOrigin } from "@/lib/env";

export async function POST(request: Request) {
  const formData = await request.formData();
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");

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
    } catch {
      // Ignore parse errors and fall back to the generic copy.
    }

    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(errorMessage)}`, request.url),
      303,
    );
  }

  const response = NextResponse.redirect(new URL("/app", request.url), 303);
  const setCookie = backendResponse.headers.get("set-cookie");
  if (setCookie) {
    response.headers.set("set-cookie", setCookie);
  }
  return response;
}
