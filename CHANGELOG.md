# Changelog

## 1.3.0 (2026-02-14)

- Multi-user accounts with local signup/bootstrap and session cookies.
- Multi-profile support (up to 8) with per-profile isolated settings/tokens.
- Real-Debrid auth and tokens fully isolated per profile (context propagated into background workers).
- Per-profile theme persistence (stored on profile + applied on switch).
- New Switch screen: pick profile, sign out, shut down.
- Profile management: rename, avatar, delete.
- Search jobs: cancellable, phased progress, per-source timings and partial results.
- Contained macOS build improvements: backend readiness wait; proper app icon; launcher hardening.
