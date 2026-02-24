# UI_COMPONENTS (v1)

## 1. Purpose
This document defines the first-pass component contract for Pluggy Discover. Components are token-driven and should not embed hardcoded design values.

## 2. Global Rules
- Use semantic props (status, tone, density) over ad-hoc booleans.
- Keep behavior separate from styling where possible.
- Ensure keyboard focus is visible and testable.
- All action components must support disabled and loading states.

## 3. Shell and Navigation

### `AppShell`
- Responsibility: shared layout, top bar, nav, responsive framing.
- Props:
  - `children: React.ReactNode`
- Notes:
  - Global search is mounted in shell.
  - Must support desktop left-nav and compact mobile behavior.

### `GlobalSearch`
- Responsibility: universal query input and submit routing.
- Props:
  - `initialQuery?: string`
  - `onSubmit?: (query: string) => void`
- States:
  - empty, valid, invalid, submitting.

## 4. Discovery Components

### `Rail`
- Responsibility: titled horizontal or grid list of result cards.
- Props:
  - `title: string`
  - `items?: ResultCardModel[]`
  - `loading?: boolean`

### `ResultCard`
- Responsibility: compact summary card for an item or bundle.
- Props:
  - `title: string`
  - `subtitle: string`
  - `thumbnailUrl?: string`
  - `onOpen?: () => void`

### `FilterBar`
- Responsibility: search refinements across protocol/provider/sort.
- Planned props:
  - `protocol: "all" | "http" | "torrent"`
  - `providers: string[]`
  - `sort: string`
  - callbacks for changes

### `SourceRow`
- Responsibility: single release/source row with metadata and CTA.
- Props:
  - `title: string`
  - `protocol: "http" | "torrent"`
  - `provider: string`
  - `size: string`
  - `seeders?: number`
  - `onSendToRd?: () => void`

### `ProtocolPill`
- Responsibility: visual protocol label.
- Props:
  - `protocol: "http" | "torrent"`

### `QualityBadge`
- Planned responsibility: release quality level chip.
- Planned props:
  - `label: string`
  - `tone?: "neutral" | "good" | "warn"`

### `TrustBadge`
- Planned responsibility: source trust indicator.
- Planned props:
  - `score: number`

## 5. Item Detail Components

### `ItemHeader`
- Responsibility: canonical item info and aliases.
- Props:
  - `title: string`
  - `aliases: string[]`
  - `updatedAt?: string`

### `ReleaseTable`
- Responsibility: release comparison surface.
- Props:
  - `rows?: SourceResultModel[]`
  - `onSendToRd?: (sourceResultId: string) => void`

### `FileTreePreview`
- Planned responsibility: preview extracted/expected file structure.
- Planned props:
  - `tree: FileNode[]`

## 6. Transfer Components

### `TransferLane`
- Responsibility: grouped transfer state column/list.
- Props:
  - `title: string`
  - `rows?: TransferModel[]`

### `TransferRow`
- Responsibility: single transfer with progress and actions.
- Props:
  - `name: string`
  - `status: string`
  - `progress?: number`
  - `onRetry?: () => void`
  - `onCancel?: () => void`

## 7. Source Management Components

### `SourceCard`
- Responsibility: provider status and controls.
- Props:
  - `name: string`
  - `status: string`
  - `lastSyncAt?: string`

### `ConnectionTestDialog`
- Planned responsibility: test source/provider connectivity.
- Planned props:
  - `open: boolean`
  - `onOpenChange: (open: boolean) => void`
  - `providerId: string`

## 8. Feedback Components

### `StatusToast`
- Planned responsibility: user notifications for queue/auth/sync events.
- Planned props:
  - `title: string`
  - `description?: string`
  - `tone?: "info" | "success" | "warning" | "error"`

## 9. Type Models (UI)

```ts
export type ResultCardModel = {
  id: string;
  title: string;
  subtitle: string;
  thumbnailUrl?: string;
};

export type SourceResultModel = {
  id: string;
  provider: string;
  protocol: "http" | "torrent";
  sizeLabel: string;
  seeders?: number;
  trustScore: number;
};

export type TransferModel = {
  id: string;
  name: string;
  status: "queued" | "resolving" | "downloading" | "completed" | "failed";
  progress: number;
};
```

## 10. Testing Requirements
- Unit test rendering + states for each component.
- Interaction test for keyboard behavior in `GlobalSearch`, `Rail`, and dialogs.
- Visual regression baseline for `ResultCard`, `SourceRow`, `TransferRow`, and `SourceCard`.
