import type { SourceResult } from "@/lib/domain/models";

export function normalizeSourceResult(raw: Record<string, unknown>): SourceResult {
  return {
    id: String(raw.id ?? ""),
    itemId: String(raw.itemId ?? ""),
    protocol: raw.protocol === "http" ? "http" : "torrent",
    provider: String(raw.provider ?? "unknown"),
    sizeBytes: Number(raw.sizeBytes ?? 0),
    seeders: raw.seeders ? Number(raw.seeders) : undefined,
    peers: raw.peers ? Number(raw.peers) : undefined,
    publishedAt: String(raw.publishedAt ?? new Date().toISOString()),
    trustScore: Number(raw.trustScore ?? 0),
    qualityLabel: String(raw.qualityLabel ?? "unknown"),
    raw
  };
}
