export function buildAppUrl(request: Request, path: string): URL {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto");
  const host = forwardedHost || request.headers.get("host");

  if (host) {
    return new URL(path, `${forwardedProto || "http"}://${host}`);
  }

  return new URL(path, request.url);
}
