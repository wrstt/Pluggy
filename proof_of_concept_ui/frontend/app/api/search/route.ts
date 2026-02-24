import { proxyJson } from "../_proxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q");
  const page = searchParams.get("page") ?? "1";
  const perPage = searchParams.get("per_page") ?? "20";
  const profile = "software";
  const includeMedia = searchParams.get("include_media") === "1";
  const platform = searchParams.get("platform") ?? "";
  const contentType = searchParams.get("content_type") ?? "";
  const licenseType = searchParams.get("license_type") ?? "";
  const fileFormat = searchParams.get("file_format") ?? "";
  const safety = searchParams.get("safety") ?? "balanced";
  const sortBy = searchParams.get("sort_by") ?? "relevance";
  const includeCustom = searchParams.get("include_custom") !== "0";
  const waitAllSources = searchParams.get("wait_all_sources") !== "0";
  const sourceTimeoutSeconds = searchParams.get("source_timeout_seconds") ?? "16";
  const cacheBust = searchParams.get("cache_bust") ?? "";

  if (!query || !query.trim()) {
    return Response.json(
      { error: { code: "BAD_REQUEST", message: "Missing q query parameter" } },
      { status: 400 }
    );
  }

  return proxyJson(request, 
    `/api/search?q=${encodeURIComponent(query)}&page=${encodeURIComponent(page)}&per_page=${encodeURIComponent(
      perPage
    )}&profile=${encodeURIComponent(profile)}${
      includeMedia ? "&include_media=true" : ""
    }&platform=${encodeURIComponent(platform)}&content_type=${encodeURIComponent(contentType)}&license_type=${encodeURIComponent(
      licenseType
    )}&file_format=${encodeURIComponent(fileFormat)}&safety=${encodeURIComponent(safety)}&sort_by=${encodeURIComponent(
      sortBy
    )}&include_custom=${includeCustom ? "true" : "false"}&wait_all_sources=${
      waitAllSources ? "true" : "false"
    }&source_timeout_seconds=${encodeURIComponent(sourceTimeoutSeconds)}&cache_bust=${encodeURIComponent(cacheBust)}`
  );
}
