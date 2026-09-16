# Architecture

Date: 2026-09-14

## Runtime

- React/Vite/TypeScript frontend served by FastAPI at `127.0.0.1:8765`.
- Python Playwright controls Google Chrome Stable in a dedicated persistent
  profile; Teams credentials stay in Chrome.
- SQLite schema v3 stores selected channels, normalized threads, FTS5 search,
  attachments/assets, capture runs and per-post checkpoints.
- Local files live under the platform user-data directory. No Microsoft Graph,
  MSAL, Google Drive or browser extension is in the MVP runtime.

## Data Flow

```text
Teams rendered DOM
  → harvest root/reply batches
  → sanitize HTML + normalize IDs
  → atomic per-post SQLite upsert
  → authenticated file capture / image capture
  → local files + capture evidence
  → React archive/search
```

## Boundaries

- Capture selectors may click only channel navigation, reply expansion, file
  `More actions`, `Download`, and reply-pane close controls.
- Composer, send, share, edit and delete actions are forbidden.
- The app never reads browser cookies/tokens into application data or calls
  undocumented Teams endpoints.
- On Windows, file capture streams the response to a rendered HTTPS SharePoint
  URL through Chrome DevTools Fetch before Chrome creates a download item. The
  response is written to a temporary local file and atomically moved into the
  archive. If streaming fails, request-context fallback may try the same
  rendered URL; a failed file remains explicitly reported. The stream has a
  bounded wait and its temporary page is closed even when a response stalls.
  This avoids a Chrome 152 download-bubble crash path observed in two Windows
  minidumps.
- On Linux, file capture still prefers the rendered Teams `Download` action and
  may use Chrome navigation for a rendered SharePoint URL if its UI card cannot
  be driven. URL response paths reject HTML/login pages, empty bodies, and
  unsupported hosts rather than storing them as files.
- One capture run owns the Chrome page at a time; channels are sequential.
- Every post commits independently. Startup marks an in-flight run interrupted;
  resume skips completed post IDs.
- The local service stays loopback-only and does not enable external CORS.

## Identity

- Message: numeric ID from `content-{id}`.
- Channel: Teams source ID from `response-surface-{source-id}` when present.
- Fallback channel: SHA-256 fingerprint of Team and channel display names,
  explicitly marked `name_fingerprint` and never auto-merged after a rename.
- Attachment/asset: SHA-256 of message ID plus source URL.

## Release

- Linux: PyInstaller onedir + `tar.zst`, built on Linux.
- Windows: PyInstaller onedir + ZIP, built on Windows.
- Both require installed Google Chrome Stable and share the same archive schema.
- Chrome profile data is platform-local and excluded from archive transfer.
