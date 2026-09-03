const appMode = (process.env.NEXT_PUBLIC_APP_MODE || process.env.APP_MODE || "desktop")
  .trim()
  .toLowerCase();

export const isDesktopMode = appMode !== "web";

export const backendOrigin =
  process.env.BACKEND_ORIGIN ||
  process.env.NEXT_PUBLIC_BACKEND_ORIGIN ||
  "http://127.0.0.1:8765";

export const sessionCookieName =
  process.env.SESSION_COOKIE_NAME || "redcap_session";
