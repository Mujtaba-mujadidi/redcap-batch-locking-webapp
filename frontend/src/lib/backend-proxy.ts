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

export async function proxyBackendGetRequest(
  request: Request,
  path: string,
): Promise<NextResponse> {
  const backendResponse = await fetch(new URL(path, backendOrigin), {
    method: "GET",
    headers: buildCookieHeaders(request, "application/json"),
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

function buildCookieHeaders(request: Request, accept: string): Headers {
  const headers = new Headers({
    accept,
  });
  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }
  return headers;
}

function parseRedirectLocation(location: string | null) {
  if (!location) {
    return {
      ok: false,
      message: "Backend action did not return a redirect.",
      redirect_path: null,
      redirect_query: {} as Record<string, string>,
      unauthorized: false,
    };
  }

  const url = new URL(location, backendOrigin);
  const redirectQuery = Object.fromEntries(url.searchParams.entries());
  const successMessage = url.searchParams.get("success");
  const importErrorMessage = url.searchParams.get("import_error");
  const errorMessage = url.searchParams.get("error") || importErrorMessage;

  return {
    ok: !errorMessage,
    message: successMessage || errorMessage,
    redirect_path: `${url.pathname}${url.search}`,
    redirect_query: redirectQuery,
    unauthorized: url.pathname === "/login",
  };
}

export async function proxyBackendFormAction(
  request: Request,
  path: string,
  body: FormData | URLSearchParams,
): Promise<NextResponse> {
  const response = await fetch(new URL(path, backendOrigin), {
    method: "POST",
    headers: buildCookieHeaders(request, "text/html"),
    body,
    cache: "no-store",
    redirect: "manual",
  });

  const parsedRedirect = parseRedirectLocation(response.headers.get("location"));
  if (parsedRedirect.unauthorized) {
    return NextResponse.json(parsedRedirect, { status: 401 });
  }

  if (response.status >= 300 && response.status < 400) {
    return NextResponse.json(parsedRedirect, {
      status: parsedRedirect.ok ? 200 : 400,
    });
  }

  if (!response.ok) {
    return NextResponse.json(
      {
        ok: false,
        message: `Backend action failed with status ${response.status}.`,
        redirect_path: null,
        redirect_query: {},
      },
      { status: response.status },
    );
  }

  return NextResponse.json(
    {
      ok: true,
      message: null,
      redirect_path: null,
      redirect_query: {},
    },
    { status: 200 },
  );
}

export async function proxyBackendDownload(
  request: Request,
  path: string,
): Promise<NextResponse> {
  const response = await fetch(new URL(path, backendOrigin), {
    method: "GET",
    headers: buildCookieHeaders(request, "*/*"),
    cache: "no-store",
    redirect: "manual",
  });

  const parsedRedirect = parseRedirectLocation(response.headers.get("location"));
  if (parsedRedirect.unauthorized) {
    return NextResponse.redirect(new URL("/login", request.url), 303);
  }

  const downloadResponse = new NextResponse(await response.arrayBuffer(), {
    status: response.status,
  });
  const contentType = response.headers.get("content-type");
  const contentDisposition = response.headers.get("content-disposition");
  if (contentType) {
    downloadResponse.headers.set("content-type", contentType);
  }
  if (contentDisposition) {
    downloadResponse.headers.set("content-disposition", contentDisposition);
  }
  return downloadResponse;
}
