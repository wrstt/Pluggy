# API_CONTRACT (v1)

## 1. Scope
This document defines the frontend-facing API surface for Pluggy Discover. Internal adapters may vary, but response envelopes should stay stable.

## 2. Common Conventions
- All responses are JSON.
- Time values use ISO-8601 UTC strings.
- Errors return `error.code`, `error.message`, and optional `error.details`.
- Pagination defaults to cursor-based format when list volume grows.

## 3. Auth and Session

### `GET /api/session`
Returns current session state and RD connection status.

Response:
```json
{
  "user": { "id": "u_123", "name": "local-user" },
  "rdConnected": true
}
```

### `POST /api/session/rd/connect`
Starts or completes Real-Debrid auth flow.

Request:
```json
{
  "deviceCode": "optional-device-code"
}
```

Response:
```json
{
  "ok": true,
  "rdConnected": true
}
```

## 4. Search and Discovery

### `GET /api/search?q={query}&protocol={all|http|torrent}&provider={id}&sort={mode}`
Returns grouped search results for software titles.

Response:
```json
{
  "query": "example",
  "groups": [
    {
      "item": {
        "id": "item_1",
        "title": "Example Package",
        "aliases": ["Example App"],
        "category": "utility",
        "updatedAt": "2026-02-13T00:00:00Z"
      },
      "sources": [
        {
          "id": "src_1",
          "itemId": "item_1",
          "protocol": "torrent",
          "provider": "indexer-a",
          "sizeBytes": 2576980377,
          "seeders": 120,
          "peers": 12,
          "publishedAt": "2026-02-12T18:00:00Z",
          "trustScore": 82,
          "qualityLabel": "stable",
          "raw": {}
        }
      ]
    }
  ]
}
```

### `GET /api/home`
Returns home rails data (popular, recent, source-driven).

Response:
```json
{
  "rails": [
    { "id": "popular", "title": "Popular Now", "items": [] },
    { "id": "recent", "title": "Recently Indexed", "items": [] }
  ],
  "health": {
    "rdConnected": true,
    "providersOnline": 4,
    "providersTotal": 5,
    "lastIndexRefreshAt": "2026-02-13T00:00:00Z"
  }
}
```

## 5. Item Detail

### `GET /api/item/{id}`
Returns canonical item data and normalized releases.

Response:
```json
{
  "item": {
    "id": "item_1",
    "title": "Example Package",
    "aliases": ["Example App"],
    "category": "utility",
    "updatedAt": "2026-02-13T00:00:00Z"
  },
  "releases": [],
  "fileTree": null
}
```

## 6. Transfers

### `GET /api/transfers?status={queued|resolving|downloading|completed|failed}`
Returns transfer queue and history slice.

Response:
```json
{
  "transfers": [
    {
      "id": "tr_1",
      "sourceResultId": "src_1",
      "status": "downloading",
      "progress": 44,
      "speed": "6.2 MB/s",
      "createdAt": "2026-02-13T00:00:00Z",
      "updatedAt": "2026-02-13T00:01:00Z"
    }
  ]
}
```

### `POST /api/transfers`
Creates a transfer by sending a selected source to RD.

Request:
```json
{
  "sourceResultId": "src_1"
}
```

Response:
```json
{
  "ok": true,
  "transfer": {
    "id": "tr_1",
    "status": "queued"
  }
}
```

### `POST /api/transfers/{id}/retry`
Retries failed transfer.

Response:
```json
{ "ok": true }
```

### `POST /api/transfers/{id}/cancel`
Cancels queued or active transfer.

Response:
```json
{ "ok": true }
```

## 7. Providers / Sources

### `GET /api/providers`
Returns configured source providers and health metrics.

Response:
```json
{
  "providers": [
    {
      "id": "indexer-a",
      "name": "Indexer A",
      "kind": "torrent-indexer",
      "enabled": true,
      "health": "healthy",
      "lastSyncAt": "2026-02-13T00:00:00Z",
      "weight": 1
    }
  ]
}
```

### `POST /api/providers`
Adds or updates provider config.

Request:
```json
{
  "name": "Indexer A",
  "kind": "torrent-indexer",
  "config": {}
}
```

Response:
```json
{
  "ok": true,
  "providerId": "indexer-a"
}
```

### `POST /api/providers/{id}/test`
Runs provider connectivity and auth test.

Response:
```json
{
  "ok": true,
  "latencyMs": 320,
  "detail": "reachable"
}
```

## 8. Error Envelope

All non-2xx responses should use:

```json
{
  "error": {
    "code": "PROVIDER_TIMEOUT",
    "message": "Provider did not respond in time",
    "details": {
      "providerId": "indexer-a"
    }
  }
}
```

## 9. Real-Debrid Integration Boundary
- Frontend never talks directly to RD with sensitive credentials.
- Next.js route handlers perform server-side proxy and token handling.
- UI always works with normalized models, not raw RD payloads.

## 10. Versioning Plan
- Start with unversioned `/api/*` for v1 in local app.
- Introduce `/api/v2/*` only for breaking payload changes.
- Maintain adapter mappers in `frontend/lib/domain/mappers.ts`.
