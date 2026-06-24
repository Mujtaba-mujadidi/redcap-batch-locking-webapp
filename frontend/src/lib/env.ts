export const backendOrigin =
  process.env.BACKEND_ORIGIN ||
  process.env.NEXT_PUBLIC_BACKEND_ORIGIN ||
  "http://localhost:8000";

export const legacyAppUrl =
  process.env.NEXT_PUBLIC_LEGACY_APP_URL || backendOrigin;

export const sessionCookieName =
  process.env.SESSION_COOKIE_NAME || "redcap_session";
