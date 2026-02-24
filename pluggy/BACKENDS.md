# Download Backends

Pluggy supports multiple download backends.

## Default: `native`
- Uses Python `requests` streaming.
- Supports pause/resume/cancel behavior in-app.
- Lowest setup overhead.

## Optional: `aria2`
- Uses local `aria2c` binary if available.
- Can improve throughput on some hosts via segmented downloads.
- If `aria2c` is not installed, Pluggy automatically falls back to `native`.
- Pause semantics are limited compared to native backend.

## Recommendation
- Keep `native` as default.
- Enable `aria2` only if you have `aria2c` installed and need higher throughput.
