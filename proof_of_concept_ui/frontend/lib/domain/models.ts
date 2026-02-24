export type Protocol = "http" | "torrent";

export type Item = {
  id: string;
  title: string;
  aliases: string[];
  category: string;
  updatedAt: string;
};

export type SourceResult = {
  id: string;
  itemId: string;
  protocol: Protocol;
  provider: string;
  sizeBytes: number;
  seeders?: number;
  peers?: number;
  publishedAt: string;
  trustScore: number;
  qualityLabel: string;
  raw: unknown;
};

export type TransferStatus = "queued" | "resolving" | "downloading" | "paused" | "completed" | "failed";

export type Transfer = {
  id: string;
  sourceResultId: string;
  status: TransferStatus;
  progress: number;
  speed?: string;
  error?: string;
  createdAt: string;
  updatedAt: string;
};

export type Provider = {
  id: string;
  name: string;
  kind: string;
  enabled: boolean;
  health: "healthy" | "degraded" | "offline";
  lastSyncAt?: string;
  weight: number;
};
