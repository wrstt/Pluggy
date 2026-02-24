# PRODUCT_UI_BRIEF (v1)

## 1. Product Direction

### Working Name
Pluggy Discover

### One-line vision
A cinematic, search-first download hub that unifies HTTP and torrent discovery, then routes selected releases to Real-Debrid for fast, reliable transfer.

### UX blend (inspired, not copied)
- Discovery model inspired by Stremio: global search, content rails, quick scan, detail drill-down.
- Visual treatment inspired by g-meh: glassy cards, subtle blur, compact utility surfaces.
- New brand posture: “power utility” for software/package retrieval, not entertainment/video.

## 2. Goals and Non-goals

### Goals
- Let users search software/titles once and see normalized results across multiple providers.
- Present source quality clearly (size, seeders, source trust, freshness, file type).
- Enable one primary action: send selected source to Real-Debrid.
- Make status obvious across queue states (queued, resolving, downloading, done, failed).
- Keep interface fast to parse with keyboard-first and remote-friendly focus behavior.

### Non-goals (v1)
- Full media-player style UI.
- Full plugin marketplace UI.
- Automated recommendation ML.
- Complex source scraping orchestration UI.

## 3. Experience Principles

1. Signal first
Only show metadata that changes decision quality.

2. Search always available
Global search must be visible in top bar on all primary screens.

3. One dominant action per card
Each result card should have one obvious primary CTA.

4. Predictable focus and keyboard navigation
Arrow/Tab navigation should be coherent in rails and dialogs.

5. Fast perceived performance
Use skeletons, optimistic queue insertion, and incremental rendering.

## 4. Information Architecture

### Primary routes
- `/` Home
- `/search?q=` Search Results
- `/item/[id]` Item Detail
- `/transfers` Transfer Queue
- `/sources` Source Manager
- `/history` Download History
- `/settings` App/Account Settings

### Global shell
- Top bar: logo, global search, source filter, sort, RD account state.
- Left nav (desktop) / bottom bar (mobile): Home, Search, Transfers, Sources, History.
- Global toasts: queue updates, auth issues, source sync outcomes.

## 5. Core Screen Specs

### Home
- Hero search surface with quick provider toggles.
- Rails:
  - Popular now
  - Recently indexed
  - From your sources
  - Resume recent workflow
- “Health” strip: provider availability, last index refresh, RD connectivity.

### Search Results
- Group by normalized title/entity.
- Inside each group, show source rows with:
  - protocol (HTTP/Torrent)
  - file size
  - seeders/peers (if torrent)
  - source trust score
  - age/freshness
- Controls: sort, protocol filter, source filter, quality presets.

### Item Detail
- Header: icon/art, canonical title, aliases, last updated.
- Release table with compact columns and quick compare.
- File tree preview (when available).
- Sticky action panel with “Send to RD” and fallback actions.

### Transfers
- Swimlanes: Queued, Resolving, Downloading, Completed, Failed.
- Row actions: retry, cancel, copy link, open destination.
- Batch actions for selected rows.

### Sources
- Connected providers list with status chip and last sync.
- Trust controls and per-source weighting.
- Add/remove source with test connection flow.

### History
- Searchable and filterable past transfers.
- Re-run transfer.
- Export events/log summary.

## 6. Visual System

### Visual identity
- Theme: cinematic utility.
- Atmosphere: dark base + translucent operational cards.
- Contrast: clear primary text and high-visibility state badges.

### Token starter set
- Color roles
  - `--bg-canvas`: deep neutral
  - `--bg-elevated`: elevated panel tone
  - `--bg-glass`: translucent surface
  - `--text-primary`
  - `--text-secondary`
  - `--accent-primary`
  - `--accent-warning`
  - `--accent-success`
  - `--border-subtle`
  - `--focus-ring`
- Radius roles
  - `--r-sm`, `--r-md`, `--r-lg`, `--r-xl`
- Spacing scale
  - `--space-1` … `--space-10`
- Motion
  - `--dur-fast: 120ms`
  - `--dur-base: 180ms`
  - `--dur-slow: 260ms`
  - easing curves for entrance/focus/exit

### Interaction patterns
- Hover: small lift + border brightening.
- Focus: explicit ring and no hidden focus states.
- Loading: skeletons per card/list cell.
- Empty states: actionable, not decorative.

## 7. Component Inventory (v1)

- `AppShell`
- `GlobalSearch`
- `FilterBar`
- `Rail`
- `ResultCard`
- `SourceRow`
- `QualityBadge`
- `TrustBadge`
- `ProtocolPill`
- `ItemHeader`
- `ReleaseTable`
- `FileTreePreview`
- `TransferLane`
- `TransferRow`
- `SourceCard`
- `ConnectionTestDialog`
- `StatusToast`

All components should support variants via tokens; no hardcoded hex/spacing values in component internals.

## 8. Data Model (UI-facing)

### Entities
- `Item`
  - `id`, `title`, `aliases[]`, `category`, `updatedAt`
- `SourceResult`
  - `id`, `itemId`, `protocol`, `provider`, `sizeBytes`, `seeders`, `peers`, `publishedAt`, `trustScore`, `qualityLabel`, `raw`
- `Transfer`
  - `id`, `sourceResultId`, `status`, `progress`, `speed`, `error`, `createdAt`, `updatedAt`
- `Provider`
  - `id`, `name`, `kind`, `enabled`, `health`, `lastSyncAt`, `weight`

### State boundaries
- `searchStore`: query, filters, sorting, grouped results.
- `transferStore`: optimistic queue + live status.
- `providerStore`: source list, health, sync events.
- `sessionStore`: auth, RD token state, permissions.

## 9. Recommended Architecture (repo-ready)

```text
frontend/
  app/
    (routes)/
      page.tsx
      search/page.tsx
      item/[id]/page.tsx
      transfers/page.tsx
      sources/page.tsx
      history/page.tsx
      settings/page.tsx
    api/
      rd/route.ts
      search/route.ts
      transfers/route.ts
    globals.css
    layout.tsx
  components/
    shell/
    search/
    result/
    item/
    transfer/
    source/
    shared/
  lib/
    api/
      rd-client.ts
      search-client.ts
      providers-client.ts
    domain/
      models.ts
      mappers.ts
      validation.ts
    state/
      search-store.ts
      transfer-store.ts
      provider-store.ts
      session-store.ts
    config/
      feature-flags.ts
  styles/
    tokens.css
    themes/
      cinematic-utility.css
      high-contrast.css
  tests/
    unit/
    integration/
    e2e/
  docs/
    PRODUCT_UI_BRIEF.md
    UI_COMPONENTS.md
    API_CONTRACT.md
```

## 10. Library Stack (real and practical)

- Framework: Next.js + React + TypeScript
- Styling: Tailwind CSS + CSS variables (tokens)
- Components: Radix UI primitives (optionally via shadcn/ui)
- Motion: Motion for React
- Data fetching: TanStack Query
- Forms: React Hook Form + Zod
- Tables/lists: TanStack Table (for release and transfer grids)
- State (if needed beyond Query): Zustand

## 11. API Integration Notes (Real-Debrid)

- Treat RD calls as server-side proxied operations where possible.
- Never expose long-lived sensitive secrets in browser code.
- Normalize provider results to a single `SourceResult` shape before render.
- Build graceful degradation for provider timeout/partial failure.

## 12. Accessibility and Quality Gates

- WCAG AA contrast for primary surfaces.
- Full keyboard path for search -> result -> transfer.
- Screen-reader labels for status chips and queue progress.
- Visual regression snapshots for primary screens.
- Lint rule to block raw color literals in component files.

## 13. Delivery Plan (v1)

### Phase 1: Foundation
- App shell, routing, tokens, theme, base components.

### Phase 2: Discovery
- Home rails + search results + filters + mock data.

### Phase 3: Transfer pipeline
- Detail view + transfer queue UI + optimistic state.

### Phase 4: Source operations
- Source manager + health + sync surface.

### Phase 5: Hardening
- Error states, accessibility pass, visual regression, perf pass.

## 14. Prompt-ready Build Spec (for LLM handoff)

"Implement a Next.js App Router UI using Tailwind + Radix primitives + Motion. Build the routes and components listed in PRODUCT_UI_BRIEF.md. Use token-driven theming from `styles/tokens.css`, avoid hardcoded visual values, and enforce keyboard-accessible rails and dialogs. Mock API boundaries first (`lib/api/*`), then wire real endpoints. Add tests for search grouping, transfer state transitions, and key interaction flows."

## 15. References

- Stremio web dependencies: https://raw.githubusercontent.com/Stremio/stremio-web/development/package.json
- Stremio design direction: https://blog.stremio.com/stremio-brand-update-app-redesign/
- g-meh live app shell: https://g-meh.com
- Next.js docs: https://nextjs.org/docs
- Tailwind docs: https://tailwindcss.com/docs
- Radix UI docs: https://www.radix-ui.com/
- Motion for React docs: https://motion.dev/docs/react
- Real-Debrid API docs: https://api.real-debrid.com/
