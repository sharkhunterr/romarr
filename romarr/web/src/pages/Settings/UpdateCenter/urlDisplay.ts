/**
 * Utilities to render a community-source URL in a compact,
 * scannable form on the Update Center table row.
 *
 * A full raw.githubusercontent.com URL is ~90+ characters — it
 * pushes the version column and action buttons off-screen on
 * mobile. The short form keeps enough context for the operator
 * to identify the source (owner/repo) without eating the row.
 */

export function shortenSourceUrl(url: string): string {
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    const parts = u.pathname.split("/").filter(Boolean);

    // GitHub raw or github.com URLs — surface just owner/repo.
    if (host.endsWith("github.com") || host.endsWith("githubusercontent.com")) {
      if (parts.length >= 2) {
        return `github.com/${parts[0]}/${parts[1]}`;
      }
      return `github.com${u.pathname}`;
    }

    // Generic: host + first path segment.
    if (parts.length > 0) {
      return `${host}/${parts[0]}${parts.length > 1 ? "/…" : ""}`;
    }
    return host;
  } catch {
    return url.length > 40 ? `${url.slice(0, 37)}…` : url;
  }
}
