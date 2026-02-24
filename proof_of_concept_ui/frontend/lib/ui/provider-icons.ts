const STATIC_PROVIDER_DOMAINS: Record<string, string> = {
  piratebay: "thepiratebay.org",
  "1337x": "1337x.to",
  http: "example.com",
  opendirectory: "duckduckgo.com",
  prowlarr: "prowlarr.com",
  "realdebrid-library": "real-debrid.com",
  rutracker: "rutracker.org",
  realdebrid: "real-debrid.com"
};

function normalizeProvider(provider?: string) {
  return (provider ?? "").toLowerCase().replace(/\s+/g, "").replace(/[^a-z0-9-]/g, "");
}

export function inferProviderDomain(provider?: string): string {
  const normalized = normalizeProvider(provider);
  if (!normalized) {
    return "";
  }
  if (STATIC_PROVIDER_DOMAINS[normalized]) {
    return STATIC_PROVIDER_DOMAINS[normalized];
  }
  if (normalized.includes("pirate")) {
    return "thepiratebay.org";
  }
  if (normalized.includes("1337")) {
    return "1337x.to";
  }
  if (normalized.includes("realdebrid")) {
    return "real-debrid.com";
  }
  if (normalized.includes("rutracker")) {
    return "rutracker.org";
  }
  if (normalized.includes("open") && normalized.includes("directory")) {
    return "duckduckgo.com";
  }
  return "";
}

export function providerFaviconUrl(provider?: string, size = 64): string {
  const domain = inferProviderDomain(provider);
  if (!domain) {
    return "";
  }
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=${size}`;
}
