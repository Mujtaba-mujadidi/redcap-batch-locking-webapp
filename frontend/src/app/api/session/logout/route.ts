import { NextResponse } from "next/server";

import { backendOrigin, sessionCookieName } from "@/lib/env";

export async function POST(request: Request) {
  const headers = new Headers({
    accept: "application/json",
  });
  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }

  const backendResponse = await fetch(new URL("/api/v1/auth/logout", backendOrigin), {
    method: "POST",
    headers,
    cache: "no-store",
  });

  const response = NextResponse.redirect(new URL("/login", request.url), 303);
  const setCookie = backendResponse.headers.get("set-cookie");
  if (setCookie) {
    response.headers.set("set-cookie", setCookie);
  } else {
    response.cookies.set({
      name: sessionCookieName,
      value: "",
      expires: new Date(0),
      path: "/",
      httpOnly: true,
      sameSite: "lax",
    });
  }
  return response;
}
