# Execution Plan: Chrome Channel Capture MVP

Date: 2026-09-14

## Status

Active — Linux local MVP implemented; Windows build and wider pilot pending.

## Outcome

Build one cross-platform desktop app that captures all visible posts, replies,
images, and downloadable files from 5–10 user-selected Teams channels through
Google Chrome, then provides an offline searchable archive.

## Authority

- Product contract: `docs/product/overview.md`
- UX contract: `docs/product/ux-spec.md`
- Browser decision: `docs/decisions/0003-browser-channel-capture.md`
- Repository workflow: `docs/WORKFLOW.md`

## Approach

1. Phase 1 — prove Chrome capture on one real channel with all 1–5 root posts: login,
   channel identity, virtualized scrolling, reply expansion, image capture,
   one file download, checkpoint, and evidence report.
2. Phase 2 — implement selected-channel setup, queue, pause/resume, retry, and
   capture all visible posts for 5–10 channels.
3. Phase 3 — integrate SQLite/FTS5 archive viewer and local attachment storage
   while preserving offline reading.
4. Phase 4 — build and validate Windows x64 and Linux x86_64 packages using
   Google Chrome Stable on both platforms.

## Risks And Recovery

- Teams UI changes: isolate selectors in one adapter and keep a captured fixture
  plus a diagnostic screenshot.
- Virtualized content: harvest each visible batch before scrolling and dedupe by
  source identifier or stable content hash.
- Uncertain completeness: compare displayed counts where available, stop only
  after stable passes, and require explicit user confirmation.
- Expired session/MFA: pause without losing checkpoint and let the user sign in.
- File failure: preserve post metadata/link and retry only the failed item.
- Browser/app interruption: commit each completed post and resume from the last
  durable checkpoint.

## Progress

- [x] Original React/FastAPI/SQLite foundation exists.
- [x] User rejected admin-dependent Microsoft Graph/RSC flows for the MVP.
- [x] User selected Google Chrome Stable on Windows and Linux.
- [x] Revised three-step setup and two-destination navigation designed.
- [x] Channel selection, capture progress, and archive viewer concepts created.
- [x] Build the isolated Chrome capture spike.
- [x] Validate all 3 root posts in one real channel: 103/103 replies, 38
  attachment references, 6 embedded images, one PNG saved, and one PDF
  downloaded without capture errors.
- [x] Validate idempotent checkpoint merge on a second visible channel: first
  run added 1 post; rerun added 0, updated 1, and retained exactly 1 post.
- [x] Validate the checkpoint rejects an incoming capture from a different
  channel instead of silently mixing data.
- [x] Implement the selected-channel queue, pause/resume, schema v3, local API,
  archive search/viewer and local attachment opening.
- [x] Build and smoke-test the Linux x86_64 portable package.
- [x] Build and smoke-test the Windows x64 portable package on Windows.
- [ ] Complete the final Windows revision against one real selected channel,
  including reply-count and attachment-file evidence.

## Validation

- Design: contrast, keyboard focus, 200% zoom, reduced motion, long channel names,
  idle/running/paused/success/partial/error states.
- Capture spike: observed channel identity, posts/replies harvested across scroll,
  one authenticated file download, restart/resume without duplicate content.
- Application: backend/frontend unit tests, lint/build, harness doctor, browser
  interaction QA, and platform packaging smoke tests.

## Current Evidence And Limit

Live Chrome automation has been validated against a real shared channel. The
rendered root/reply selectors and download menu worked for that channel, but
selector stability across additional channels and future Teams UI versions is
not yet proven. The pilot output is stored outside Git under the user's local
application-data directory.

## Phase 1 Pilot Result

- Real channel A: 3 root posts, 103/103 replies matched, 38 attachment
  references, 6 embedded images, and zero extractor errors.
- Asset proof: one valid one-page PDF downloaded through the Teams UI and one
  rendered embedded image saved as PNG.
- Offline proof: capture JSON rendered into a script-free HTML preview and a
  separate count/error report.
- Recovery proof: atomic checkpoint merge passed unit tests, deduplicated a
  real rerun, and rejected cross-channel contamination.

## Local MVP Implementation Result

- Schema v3, normalized capture persistence, FTS5 archive search, per-run,
  per-channel and per-post checkpoints implemented with v1 migration.
- Production Playwright Python session opens Google Chrome Stable, detects
  sign-in without blocking API status, navigates virtualized channels through
  Teams `Ctrl+Alt+G`, and supports both reply-pane and inline-reply layouts.
- Live production run on a real channel captured 1 root post and 3/3 replies.
  One attachment downloaded locally; five UI attachments without a successful
  Download path were preserved as failures, and the run correctly ended
  `partial` with `attachment-failures` rather than claiming completion.
- Live pause/resume observed `running → paused → running → partial`; a manual
  rerun kept message/attachment row counts stable.
- React setup, capture progress and archive reader implemented and compared to
  accepted concepts at 1586×992. Archive remains operable without horizontal
  overflow at 1024px and a 793px large-zoom equivalent.
- Linux PyInstaller onedir and `tar.zst` build succeeded and served both
  `/api/health` and the packaged frontend. Windows build script exists but has
  not run on Windows.

## Final Validation Snapshot

- Backend: 16 pytest cases pass, including schema migration, idempotency,
  sanitization, DOM selectors, inline replies and forbidden-action ownership.
- Frontend: Vitest pass, ESLint pass, production Vite build pass, npm audit
  reports 0 vulnerabilities.
- Browser QA: page identity, meaningful DOM, error recovery, capture progress,
  archive search/detail, 1586×992 concept comparison, 1024px layout and 793px
  large-zoom equivalent pass; final clean session has 0 console errors/warnings.
- Package QA: final Linux archive contains executable and README; packaged
  health/status/frontend smoke pass.
- Linux artifact SHA-256:
  `533642f57376a419cd96121b0ce131cacb0aea4b8a59c18eaca6c064d46cdc32`.
- Windows package QA: onedir builds and Playwright self-tests pass. Smart App
  Control allowed an intermediate console build but blocked one unsigned GUI
  hash, so trusted code signing remains a release requirement for predictable
  distribution.
- Linux production verification now covers three channels: 10 root posts,
  587/587 displayed replies, 151/151 attachment references, and 18/18 hosted
  images. All recorded files/assets are non-empty, all three runs completed with
  zero failed/pending files, and an idempotent rerun did not add database rows.
- Remaining: run the final Windows revision across one complete selected channel
  and verify posts, replies, downloaded files, offline opening, and idempotency
  before closing this plan.
