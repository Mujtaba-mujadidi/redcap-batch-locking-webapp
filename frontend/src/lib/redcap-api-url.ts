export const ALLOWED_REDCAP_API_URLS = [
  "https://stg.ovg.ox.ac.uk/COVID-19-stg/api/",
  "https://apps.ovg.ox.ac.uk/redcap/api/",
  "https://pms.ovg.ox.ac.uk/api/",
  "http://localhost:8888/redcap/api/",
] as const;

export const UNAUTHORIZED_REDCAP_API_URL_MESSAGE =
  "The REDCap API URL you entered is not approved for this app. Please contact the Development team at the Oxford Vaccine Group if you need access.";

export function normalizeRedcapApiUrlForAllowlist(apiUrl: string): string {
  try {
    const parsed = new URL(apiUrl.trim());
    let path = parsed.pathname || "/";
    if (!path.endsWith("/")) {
      path = `${path}/`;
    }
    return `${parsed.protocol}//${parsed.host}${path}`.toLowerCase();
  } catch {
    return "";
  }
}

const ALLOWED_REDCAP_API_URL_KEYS = new Set(
  ALLOWED_REDCAP_API_URLS.map((url) => normalizeRedcapApiUrlForAllowlist(url)),
);

export function isAllowedRedcapApiUrl(apiUrl: string): boolean {
  const normalized = normalizeRedcapApiUrlForAllowlist(apiUrl);
  return Boolean(normalized) && ALLOWED_REDCAP_API_URL_KEYS.has(normalized);
}
