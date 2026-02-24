"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ProtocolPill } from "@/components/shared/ProtocolPill";
import { ProviderAwareIcon } from "@/lib/ui/provider-aware-icon";

type SearchSource = {
  id: string;
  itemId: string;
  protocol: "http" | "torrent";
  provider: string;
  sizeBytes: number;
  seeders?: number;
  trustScore?: number;
  raw?: {
    description?: string;
    contentType?: string;
    licenseType?: string;
    platforms?: string[];
    formats?: string[];
    tags?: string[];
    linkCandidates?: Array<{ url?: string }>;
  };
};

type SearchGroup = {
  item: { id: string; title: string };
  sources: SearchSource[];
};

type TransferQueueItem = {
  sourceResultId: string;
  status: string;
};

type ProviderState = {
  id: string;
  name: string;
  enabled: boolean;
  health: string;
};

type SearchJobSourceState = {
  status: string;
  warning?: string;
  elapsedMs?: number;
  attempts?: number;
};

type SearchJobPayload = {
  id: string;
  query: string;
  status: string;
  phase: "init" | "querying" | "ranking" | "done";
  mode: "fast" | "deep";
  partial: boolean;
  message?: string;
  progress?: { totalSources?: number; completedSources?: number; firstResultAt?: string | null };
  timings?: { wallMs?: number; cpuMs?: number };
  sources?: Record<string, SearchJobSourceState>;
  result?: { groups?: SearchGroup[]; count?: number; page?: number; perPage?: number; hasMore?: boolean };
};

type Filters = {
  sourceType: string;
  platform: string;
  contentType: string;
  licenseType: string;
  fileFormat: string;
  safety: "strict" | "balanced" | "open";
  sortBy: "relevance" | "seeds" | "size" | "trust" | "title";
  includeMedia: boolean;
};

type DisplaySort = "best" | "provider" | "source-type";

const SOURCE_TYPE_OPTIONS = ["torrent", "http", "opendirectory", "1337x", "piratebay", "curated"] as const;
const PLATFORM_OPTIONS = ["windows", "mac", "linux", "android", "emulator"] as const;
const FORMAT_OPTIONS = ["installer", "zip", "7z", "iso", "dmg", "pkg"] as const;
const SORT_OPTIONS: Array<{ id: Filters["sortBy"]; label: string }> = [
  { id: "relevance", label: "Best Match" },
  { id: "seeds", label: "Most Seeds" },
  { id: "trust", label: "Highest Trust" },
  { id: "size", label: "Smallest Size" },
  { id: "title", label: "Title A-Z" }
];

function csvSet(value: string): Set<string> {
  return new Set(
    (value || "")
      .split(",")
      .map((part) => part.trim().toLowerCase())
      .filter(Boolean)
  );
}

function csvWithToggle(value: string, token: string): string {
  const set = csvSet(value);
  if (set.has(token)) {
    set.delete(token);
  } else {
    set.add(token);
  }
  return Array.from(set).join(",");
}

function formatSize(sizeBytes: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Number(sizeBytes) || 0;
  for (const unit of units) {
    if (value < 1024) {
      return `${value.toFixed(2)} ${unit}`;
    }
    value /= 1024;
  }
  return `${value.toFixed(2)} PB`;
}

function rdButtonLabel(status?: string, isSubmitting?: boolean) {
  if (isSubmitting) return "Sending…";
  if (!status) return "Send to RD";
  if (status === "completed") return "Done";
  if (status === "downloading" || status === "paused") return "In Transfer";
  if (status === "queued" || status === "resolving") return "Queued";
  return "Sent";
}

function ChipGroup({
  title,
  options,
  value,
  onToggle
}: {
  title: string;
  options: readonly string[];
  value: string;
  onToggle: (token: string) => void;
}) {
  const selected = csvSet(value);
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-2">
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{title}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onToggle(option)}
            className={`rounded border px-2 py-1 text-xs ${
              selected.has(option)
                ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/20 text-zinc-50"
                : "border-white/20 bg-white/5 text-zinc-300"
            }`}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SearchResultsClient({ query, runToken }: { query: string; runToken?: string }) {
  const [groups, setGroups] = useState<SearchGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [queuedBySourceId, setQueuedBySourceId] = useState<Record<string, string>>({});
  const [filters, setFilters] = useState<Filters>({
    sourceType: "",
    platform: "",
    contentType: "",
    licenseType: "",
    fileFormat: "",
    safety: "balanced",
    sortBy: "relevance",
    includeMedia: false
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [displaySort, setDisplaySort] = useState<DisplaySort>("best");
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [scanStep, setScanStep] = useState(0);
  const [providers, setProviders] = useState<ProviderState[]>([]);
  const [job, setJob] = useState<SearchJobPayload | null>(null);
  const [searchMode, setSearchMode] = useState<"fast" | "deep">("deep");

  useEffect(() => {
    try {
      setShowAdvanced(window.localStorage.getItem("platswap:search-advanced") === "1");
    } catch {}
  }, []);

  useEffect(() => {
    if (!loading) return;
    setScanStep(0);
    const timer = setInterval(() => {
      setScanStep((prev) => prev + 1);
    }, 560);
    return () => clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    let cancelled = false;

    const refreshTransfers = async () => {
      try {
        const response = await fetch("/api/transfers", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || !Array.isArray(payload.transfers)) {
          return;
        }
        if (cancelled) {
          return;
        }
        const map: Record<string, string> = {};
        for (const transfer of payload.transfers as TransferQueueItem[]) {
          const sourceResultId = String(transfer?.sourceResultId || "");
          const status = String(transfer?.status || "");
          if (!sourceResultId) {
            continue;
          }
          if (status === "failed") {
            continue;
          }
          map[sourceResultId] = status || "queued";
        }
        setQueuedBySourceId(map);
      } catch {
        // no-op: search can still function if transfer polling fails
      }
    };

    refreshTransfers();
    const timer = setInterval(refreshTransfers, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refreshProviders = async () => {
      try {
        const response = await fetch("/api/providers", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || !Array.isArray(payload.providers) || cancelled) {
          return;
        }
        setProviders(
          payload.providers
            .map((provider: Record<string, unknown>) => ({
              id: String(provider.id || ""),
              name: String(provider.name || ""),
              enabled: Boolean(provider.enabled),
              health: String(provider.health || "unknown").toLowerCase(),
            }))
            .filter((provider: ProviderState) => provider.name.toLowerCase() !== "rutracker")
        );
      } catch {
        // non-fatal
      }
    };

    refreshProviders();
    const timer = setInterval(refreshProviders, 12000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!query) {
      setGroups([]);
      setJob(null);
      setCurrentPage(1);
      setHasMore(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotice(null);

    const startJob = async (): Promise<string> => {
      const effective: Filters = { ...filters };
      const response = await fetch("/api/search/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          q: query,
          page: currentPage,
          per_page: pageSize,
          include_media: effective.includeMedia,
          include_custom: true,
          mode: searchMode,
          cache_bust: runToken || `${Date.now()}`
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error?.message ?? "Search failed to start");
      }
      return String(payload?.jobId || "");
    };

    const pollJob = async (jobId: string) => {
      let lastCount = 0;
      for (;;) {
        if (cancelled) return;
        const response = await fetch(`/api/search/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
        const payload = (await response.json()) as SearchJobPayload;
        if (!response.ok) {
          throw new Error((payload as any)?.error?.message ?? "Search status failed");
        }
        if (cancelled) return;
        setJob(payload);
        const nextGroups = Array.isArray(payload?.result?.groups) ? (payload.result!.groups as SearchGroup[]) : [];
        const nextCount = Number(payload?.result?.count ?? 0);
        setGroups(nextGroups);
        setHasMore(Boolean(payload?.result?.hasMore));

        if (lastCount === 0 && nextCount > 0) {
          setNotice("First results are in. Continuing deep scan…");
        }
        lastCount = nextCount;

        const status = String(payload?.status || "");
        if (status === "done") {
          setNotice("Search complete.");
          return;
        }
        if (status === "cancelled") {
          setNotice("Search cancelled. Keeping partial results.");
          return;
        }
        if (status === "error") {
          throw new Error(payload?.message || "Search failed");
        }
        await new Promise((r) => setTimeout(r, payload?.phase === "querying" ? 650 : 900));
      }
    };

    (async () => {
      try {
        const jobId = await startJob();
        if (!jobId) throw new Error("Search job id missing");
        if (cancelled) return;
        await pollJob(jobId);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Search failed");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [query, runToken, filters, currentPage, pageSize, searchMode]);

  const sourceRows = useMemo(
    () =>
      groups.flatMap((group) =>
        group.sources.map((source) => ({ source, title: group.item.title, itemId: group.item.id }))
      ),
    [groups]
  );

  const filteredRows = useMemo(() => {
    const requested = csvSet(filters.sourceType);
    if (requested.size === 0) {
      return sourceRows;
    }
    return sourceRows.filter(({ source }) => {
      const provider = (source.provider || "").toLowerCase();
      for (const token of requested) {
        if (token === "torrent" && source.protocol === "torrent") return true;
        if (token === "http" && source.protocol === "http") return true;
        if (token === "opendirectory" && provider.includes("opendirectory")) return true;
        if (token === "1337x" && provider.includes("1337x")) return true;
        if (token === "piratebay" && provider.includes("piratebay")) return true;
        if (token === "curated" && provider.includes("curated")) return true;
      }
      return false;
    });
  }, [sourceRows, filters.sourceType]);

  const sortedRows = useMemo(() => {
    const next = [...filteredRows];
    if (displaySort === "provider") {
      next.sort((a, b) => {
        const byProvider = a.source.provider.localeCompare(b.source.provider, undefined, { sensitivity: "base" });
        if (byProvider !== 0) return byProvider;
        return (b.source.seeders ?? 0) - (a.source.seeders ?? 0);
      });
      return next;
    }
    if (displaySort === "source-type") {
      next.sort((a, b) => {
        const aRank = a.source.protocol === "torrent" ? 0 : 1;
        const bRank = b.source.protocol === "torrent" ? 0 : 1;
        if (aRank !== bRank) return aRank - bRank;
        const byProvider = a.source.provider.localeCompare(b.source.provider, undefined, { sensitivity: "base" });
        if (byProvider !== 0) return byProvider;
        return (b.source.seeders ?? 0) - (a.source.seeders ?? 0);
      });
      return next;
    }
    return next;
  }, [filteredRows, displaySort]);

  useEffect(() => {
    if (loading) return;
    if (!filters.sourceType.trim()) return;
    if (sourceRows.length === 0) return;
    if (filteredRows.length > 0) return;
    setFilters((prev) => ({ ...prev, sourceType: "" }));
    setNotice("Source filter had no matches. Showing all sources.");
  }, [loading, filters.sourceType, sourceRows.length, filteredRows.length]);

  useEffect(() => {
    setCurrentPage(1);
  }, [query, runToken, filters, pageSize]);

  async function sendToRd(sourceResultId: string) {
    const existing = queuedBySourceId[sourceResultId];
    if (existing && existing !== "failed") {
      setNotice(`Already sent to RD (${existing}). Check Transfers.`);
      return;
    }

    setSubmittingId(sourceResultId);
    setError(null);
    setNotice(null);
    try {
      // Optimistic queue state blocks duplicate sends immediately.
      setQueuedBySourceId((prev) => ({ ...prev, [sourceResultId]: "queued" }));
      const response = await fetch("/api/rd", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceResultId })
      });
      const payload = await response.json();
      if (!response.ok) {
        setQueuedBySourceId((prev) => {
          const next = { ...prev };
          delete next[sourceResultId];
          return next;
        });
        throw new Error(payload?.error?.message ?? "Send to RD failed");
      }
      const transferStatus = String(payload?.transfer?.status || "queued");
      setQueuedBySourceId((prev) => ({ ...prev, [sourceResultId]: transferStatus }));
      setNotice("Sent to RD. Tracking in Transfers.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Send to RD failed");
    } finally {
      setSubmittingId(null);
    }
  }

  function toggleAdvanced() {
    const next = !showAdvanced;
    setShowAdvanced(next);
    try {
      window.localStorage.setItem("platswap:search-advanced", next ? "1" : "0");
    } catch {}
  }

  const quickSourceMode = useMemo(() => {
    const raw = filters.sourceType.trim().toLowerCase();
    if (!raw) return "all";
    if (raw === "torrent") return "torrent";
    if (raw === "http") return "http";
    if (raw === "opendirectory") return "opendirectory";
    return "custom";
  }, [filters.sourceType]);

  const sourceScanLanes = useMemo(() => {
    const torrentHits = sourceRows.filter((row) => row.source.protocol === "torrent").length;
    const httpHits = sourceRows.filter((row) => row.source.protocol === "http").length;
    const odHits = sourceRows.filter((row) => row.source.provider.toLowerCase().includes("opendirectory")).length;
    const phase = scanStep % 3;
    return [
      {
        id: "torrent",
        label: "Torrent sources",
        hits: torrentHits,
        active: loading && phase === 0
      },
      {
        id: "http",
        label: "HTTP sources",
        hits: httpHits,
        active: loading && phase === 1
      },
      {
        id: "od",
        label: "OpenDirectory",
        hits: odHits,
        active: loading && phase === 2
      }
    ];
  }, [sourceRows, loading, scanStep]);

  function setQuickSourceMode(mode: "all" | "torrent" | "http" | "opendirectory") {
    if (mode === "all") {
      setFilters((prev) => ({ ...prev, sourceType: "" }));
      return;
    }
    setFilters((prev) => ({ ...prev, sourceType: mode }));
  }

  async function toggleProvider(providerId: string, enabled: boolean) {
    try {
      const response = await fetch(`/api/providers/${encodeURIComponent(providerId)}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) {
        return;
      }
      setProviders((prev) => prev.map((provider) => (provider.id === providerId ? { ...provider, enabled } : provider)));
      setNotice(`Source ${enabled ? "enabled" : "disabled"}.`);
    } catch {
      // non-fatal
    }
  }

  const degradedProviders = useMemo(
    () => providers.filter((provider) => provider.enabled && provider.health !== "healthy"),
    [providers]
  );

  async function cancelSearch() {
    const jobId = job?.id;
    if (!jobId) return;
    try {
      await fetch(`/api/search/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
    } catch {
      // non-fatal
    }
  }

  return (
    <>
      <p className="text-sm text-zinc-300">{query ? `Query: ${query}` : "Use the header search box to begin."}</p>
      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs uppercase tracking-wide text-zinc-400">Search Controls</p>
          <button onClick={toggleAdvanced} className="btn-secondary px-2 py-1 text-xs">
            {showAdvanced ? "Hide Advanced" : "Show Advanced"}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setSearchMode("fast")}
            className={`rounded-full border px-3 py-1 text-xs transition ${
              searchMode === "fast"
                ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/25 text-zinc-50"
                : "border-white/20 bg-black/20 text-zinc-200 hover:bg-black/30"
            }`}
          >
            Fast
          </button>
          <button
            type="button"
            onClick={() => setSearchMode("deep")}
            className={`rounded-full border px-3 py-1 text-xs transition ${
              searchMode === "deep"
                ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/25 text-zinc-50"
                : "border-white/20 bg-black/20 text-zinc-200 hover:bg-black/30"
            }`}
          >
            Deep
          </button>
          <p className="text-xs text-zinc-400">Deep search can take 10–120 seconds depending on sources.</p>
          {loading && job?.id ? (
            <button
              type="button"
              onClick={cancelSearch}
              className="ml-auto rounded-full border border-white/20 bg-black/20 px-3 py-1 text-xs hover:bg-black/30"
            >
              Cancel
            </button>
          ) : null}
        </div>
        <p className="mt-2 text-xs text-zinc-400">
          Primary mode uses all enabled sources automatically. Use source lane buttons only to narrow temporarily.
        </p>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-black/25 p-2.5">
            <p className="text-[11px] uppercase tracking-wide text-zinc-400">Source Lane</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button onClick={() => setQuickSourceMode("all")} className={`btn-secondary px-3 py-1.5 text-xs ${quickSourceMode === "all" ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15" : ""}`}>All Sources</button>
              <button onClick={() => setQuickSourceMode("torrent")} className={`btn-secondary px-3 py-1.5 text-xs ${quickSourceMode === "torrent" ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15" : ""}`}>Torrent</button>
              <button onClick={() => setQuickSourceMode("http")} className={`btn-secondary px-3 py-1.5 text-xs ${quickSourceMode === "http" ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15" : ""}`}>HTTP</button>
              <button onClick={() => setQuickSourceMode("opendirectory")} className={`btn-secondary px-3 py-1.5 text-xs ${quickSourceMode === "opendirectory" ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15" : ""}`}>OpenDirectory</button>
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/25 p-2.5">
            <p className="text-[11px] uppercase tracking-wide text-zinc-400">Sort Results</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {SORT_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setFilters((prev) => ({ ...prev, sortBy: option.id }))}
                  className={`btn-secondary px-3 py-1.5 text-xs ${filters.sortBy === option.id ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15" : ""}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setFilters((prev) => ({ ...prev, includeMedia: !prev.includeMedia }))}
            className={`btn-secondary px-3 py-1.5 text-xs ${filters.includeMedia ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15" : ""}`}
          >
            Include Movie/TV
          </button>
        </div>
        {showAdvanced ? (
          <>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <ChipGroup
                title="Platform"
                options={PLATFORM_OPTIONS}
                value={filters.platform}
                onToggle={(token) => setFilters((prev) => ({ ...prev, platform: csvWithToggle(prev.platform, token) }))}
              />
              <ChipGroup
                title="Format"
                options={FORMAT_OPTIONS}
                value={filters.fileFormat}
                onToggle={(token) => setFilters((prev) => ({ ...prev, fileFormat: csvWithToggle(prev.fileFormat, token) }))}
              />
            </div>
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={() =>
                  setFilters((prev) => ({
                    ...prev,
                    sourceType: "",
                    platform: "",
                    contentType: "",
                    licenseType: "",
                    fileFormat: "",
                    safety: "balanced",
                    sortBy: "relevance",
                    includeMedia: false
                  }))
                }
                className="btn-secondary px-2 py-1 text-xs"
              >
                Reset Advanced
              </button>
            </div>
          </>
        ) : null}
      </div>
      {loading || query ? (
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="mb-2 flex items-center justify-between text-xs text-zinc-300">
            <span>{loading ? "Scanning sources..." : "Source scan summary"}</span>
            <span>{loading ? "live" : "complete"}</span>
          </div>
          <div className="space-y-2">
            {sourceScanLanes.map((lane) => (
              <div key={lane.id} className={`source-scan-row ${lane.active ? "is-active" : ""}`}>
                <div className="flex items-center justify-between text-xs">
                  <span>{lane.label}</span>
                  <span>{lane.hits} hits</span>
                </div>
                <div className="source-scan-track">
                  <div className={`source-scan-fill ${lane.active ? "is-active" : ""}`} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="rounded-xl border border-white/10 bg-white/5 p-3">
        <div className="mb-2 flex items-center justify-between text-xs text-zinc-300">
          <span>Source health ticker</span>
          <span>{degradedProviders.length === 0 ? "all healthy" : `${degradedProviders.length} need attention`}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {providers.map((provider) => {
            const degraded = provider.health !== "healthy";
            return (
              <button
                key={provider.id}
                type="button"
                onClick={() => toggleProvider(provider.id, !provider.enabled)}
                className={`rounded-lg border px-2.5 py-1 text-xs ${
                  provider.enabled
                    ? degraded
                      ? "border-amber-400/60 bg-amber-500/15 text-amber-100"
                      : "border-emerald-400/45 bg-emerald-500/10 text-emerald-100"
                    : "border-zinc-400/45 bg-zinc-700/20 text-zinc-200"
                }`}
                title={`Click to ${provider.enabled ? "disable" : "enable"} ${provider.name}`}
              >
                {provider.name} • {provider.enabled ? provider.health : "disabled"}
              </button>
            );
          })}
        </div>
      </div>
      {loading ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-zinc-300">
            Searching… {job?.phase ? <span className="text-zinc-400">({job.phase})</span> : null}
          </p>
          {job?.progress ? (
            <p className="text-xs text-zinc-400">
              {Number(job.progress.completedSources ?? 0)}/{Number(job.progress.totalSources ?? 0)} sources
            </p>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      {notice ? <p className="text-sm text-emerald-300">{notice}</p> : null}
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-300">
            <span>{sortedRows.length} results</span>
            <span className="text-zinc-500">•</span>
            <span>Page {currentPage}</span>
            <span className="text-zinc-500">•</span>
            <span>
              {job?.partial ? "Partial results (still scanning)" : "All enabled sources"}
            </span>
            {job?.timings?.wallMs ? (
              <>
                <span className="text-zinc-500">•</span>
                <span>{Math.round(Number(job.timings.wallMs) / 100) / 10}s</span>
              </>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <label className="text-zinc-300">
              Result Order
              <select
                className="ml-2 rounded border border-white/20 bg-black/30 px-2 py-1"
                value={displaySort}
                onChange={(event) => setDisplaySort(event.target.value as DisplaySort)}
              >
                <option value="best">best match</option>
                <option value="provider">provider</option>
                <option value="source-type">source type</option>
              </select>
            </label>
            <label className="text-zinc-300">
              Per Page
              <select
                className="ml-2 rounded border border-white/20 bg-black/30 px-2 py-1"
                value={String(pageSize)}
                onChange={(event) => setPageSize(Math.max(5, Number(event.target.value) || 20))}
              >
                <option value="10">10</option>
                <option value="20">20</option>
                <option value="30">30</option>
                <option value="50">50</option>
              </select>
            </label>
            <button
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage <= 1}
              className="btn-secondary px-2 py-1 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={() => setCurrentPage((prev) => prev + 1)}
              disabled={!hasMore}
              className="btn-secondary px-2 py-1 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
        {sortedRows.length === 0 && !loading ? <p className="text-sm text-zinc-300">No results.</p> : null}
        {sortedRows.map(({ source, title, itemId }) => (
          <article key={source.id} className="motion-soft mb-3 rounded-lg border border-white/10 bg-white/5 p-3 last:mb-0">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <ProviderAwareIcon title={title} provider={source.provider} protocol={source.protocol} size={36} />
                <div>
                  <h2 className="text-sm font-semibold">
                    <Link href={`/item/${encodeURIComponent(itemId)}`} className="hover:underline">
                      {title}
                    </Link>
                  </h2>
                  <p className="text-xs text-zinc-400">{source.provider}</p>
                  {source.raw?.description ? <p className="text-xs text-zinc-500">{source.raw.description}</p> : null}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <ProtocolPill protocol={source.protocol} />
                <span className="text-zinc-300">{formatSize(source.sizeBytes)}</span>
                <span className="text-zinc-300">Seeds: {source.seeders ?? 0}</span>
                <span className="rounded border border-white/20 bg-black/30 px-2 py-0.5 text-zinc-200">
                  Trust {source.trustScore ?? 0}
                </span>
                <button
                  onClick={() => sendToRd(source.id)}
                  disabled={submittingId === source.id || Boolean(queuedBySourceId[source.id])}
                  className={`px-2 py-1 text-xs ${
                    queuedBySourceId[source.id] ? "btn-secondary opacity-90" : "btn-primary"
                  }`}
                >
                  {rdButtonLabel(queuedBySourceId[source.id], submittingId === source.id)}
                </button>
                {source.protocol === "http" ? (
                  <a
                    href={source.raw?.linkCandidates?.[0]?.url ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-secondary px-2 py-1 text-xs"
                  >
                    Open Link
                  </a>
                ) : null}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-zinc-300">
              {(source.raw?.platforms || []).slice(0, 4).map((platform) => (
                <span key={platform} className="rounded border border-white/20 bg-black/30 px-1.5 py-0.5">
                  {platform}
                </span>
              ))}
              {(source.raw?.tags || []).slice(0, 4).map((tag) => (
                <span key={tag} className="rounded border border-white/20 bg-black/30 px-1.5 py-0.5">
                  {tag}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
