import { cookies } from "next/headers";

import { backendOrigin } from "@/lib/env";
import type { SessionEnvelope } from "@/lib/types";

export class BackendRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "BackendRequestError";
    this.status = status;
  }
}

function joinUrl(baseUrl: string, path: string): string {
  return new URL(path, baseUrl).toString();
}

async function buildCookieHeader(): Promise<string> {
  const cookieStore = await cookies();
  return cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string; message?: string };
    return body.detail || body.message || `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export async function fetchBackend(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const cookieHeader = await buildCookieHeader();

  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }
  if (!headers.has("accept")) {
    headers.set("accept", "application/json");
  }

  return fetch(joinUrl(backendOrigin, path), {
    ...init,
    headers,
    cache: init.cache ?? "no-store",
  });
}

export async function fetchBackendJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetchBackend(path, init);
  } catch (error) {
    // Preserve Next.js dynamic-rendering signals (cookies()/headers()).
    if (
      error instanceof Error &&
      (error.message.includes("Dynamic server usage") ||
        error.message.includes("couldn't be rendered statically") ||
        error.message.includes("used `cookies`"))
    ) {
      throw error;
    }
    const detail = error instanceof Error ? error.message : "network error";
    throw new BackendRequestError(`Could not reach the local API (${detail}).`, 503);
  }
  if (!response.ok) {
    throw new BackendRequestError(await extractErrorMessage(response), response.status);
  }
  return (await response.json()) as T;
}

export async function getSession(): Promise<SessionEnvelope | null> {
  const response = await fetchBackend("/api/v1/auth/me");
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new BackendRequestError(await extractErrorMessage(response), response.status);
  }
  return (await response.json()) as SessionEnvelope;
}

export async function requireSession(): Promise<SessionEnvelope> {
  const session = await getSession();
  if (session === null) {
    throw new BackendRequestError("Desktop session is unavailable.", 503);
  }
  return session;
}
