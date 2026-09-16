# Windows troubleshooting and fix history

Date: 2026-09-15

This document records the Windows failures investigated after the first GitHub
Actions build, the changes made in the repository, the evidence collected, and
the remaining release limitations. Intermediate local ZIP files were diagnostic
builds, not verified releases.

## Current status

- The source contains fixes for the packaging, Windows path, retry, Teams DOM,
  Chrome recovery, and status-polling failures described below.
- Backend tests, frontend tests, lint, frontend production build, PyInstaller
  build, packaged self-test, and local health checks have passed at different
  stages of the investigation.
- Linux production capture is verified on three selected Teams channels. The
  exact final Windows package still requires a smoke run before describing the
  Windows artifact as end-to-end verified.
- A Windows 0.3.0 capture crashed Chrome after its first thread. The cause of
  that Chrome allocation failure is still unknown. A separate navigation
  recovery defect then caused `channel-not-visible` on both selected channels.
- GitHub Actions builds are unsigned. Removing the known blocked native module
  reduces Smart App Control failures, but it does not provide the guarantee of
  a trusted code-signing certificate.

## Failure history

### 1. GitHub artifact failed while importing `nh3`

Observed error:

```text
ImportError: DLL load failed while importing nh3:
An Application Control policy has blocked this file.
```

Evidence:

- The downloaded Actions ZIP matched the workflow artifact by SHA-256, so it was
  not a damaged or substituted download.
- Windows Code Integrity events 3033 and 3077 named `_internal/nh3/nh3.pyd` and
  policy `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`.
- The executable and `nh3.pyd` were unsigned. Removing `Zone.Identifier` did not
  make the native extension load under the active policy.

Repository fix:

- Replaced native `nh3` with pure-Python `bleach` for stored HTML sanitization.
- Preserved the allowlist of tags, attributes, and URL schemes; added tests for
  scripts, event handlers, and `javascript:` URLs.
- Removed `uvicorn[standard]` native extras and selected the asyncio loop and h11
  HTTP implementation explicitly.
- Reduced PyInstaller hidden imports to the implementations used at runtime.

Limit:

The application executable is still unsigned. A new GUI executable hash was
observed being blocked by Smart App Control while a console build of the same
source passed locally. Reliable distribution to another Windows machine
requires a trusted code-signing process; repository changes cannot manufacture
publisher trust.

### 2. Actions artifact required two extraction steps

Cause:

The build script created a ZIP and `actions/upload-artifact` wrapped that ZIP in
another artifact archive.

Repository fix:

The workflow now uploads `dist/Teams Offline Archive` directly. A downloaded
artifact needs one extraction before running the executable.

### 3. Packaged application had no meaningful runtime smoke test

Cause:

The workflow proved that PyInstaller produced files, but did not prove that the
packaged Python and Playwright driver could start.

Repository fix:

- Added `--self-test` to start and stop the packaged Playwright driver.
- Added the packaged self-test to `scripts/build-windows.ps1` before archive
  creation.

Limit:

This is a packaging smoke test. It does not log in to Teams or prove capture.

### 4. Windows rejected the attachment storage directory

Observed error:

```text
[WinError 123] The filename, directory name, or volume label syntax is incorrect:
...\\files\\ui-channel:<hash>\\<attachment-hash>
```

Cause:

The logical channel ID `ui-channel:<hash>` was used directly as a directory
name. A colon is invalid in a Windows filename component.

Repository fix:

- Added `storage_key()`, a deterministic 32-character hexadecimal key derived
  from the logical channel ID.
- Applied it to both attachment and hosted-image directories.
- Kept the original channel ID in SQLite; only the filesystem representation is
  changed.

Existing failed rows are updated when the channel is captured again; deleting
the archive database is not required.

### 5. An old background instance made a new build appear unchanged

Observed behavior:

A process from an older extracted directory still owned `127.0.0.1:8765`.
Opening another executable displayed the page served by the old process, so old
errors and behavior remained visible.

Operational resolution:

Before switching builds, end the existing `Teams Offline Archive.exe` process,
then extract the new build into a separate directory and run it. Closing only
the browser tab does not stop the local server.

Remaining improvement:

The application does not yet provide a single-instance handoff or a clear
"another version is already running" message.

### 6. Per-channel **Retry** resumed a finished run instead of retrying

Cause:

The row button called `/resume` for a run whose final status was `partial` or
`failed`. The backend only resumes active interrupted or paused runs, so no new
capture occurred.

Repository fix:

- `startCapture()` now accepts optional channel IDs.
- A row retry creates a new run scoped to that failed channel.
- Retry is hidden while another run is active and disabled while its request is
  being submitted.
- Added a frontend test for the scoped request body.

### 7. Teams no longer exposed `channel-pane-viewport`

Observed error:

```text
Timeout 15000ms exceeded while waiting for
locator("[data-tid=\"channel-pane-viewport\"]")
```

Evidence:

The app reported a signed-in Teams session and the expected current channel
title, but the fixed viewport selector never became visible.

Repository fix:

- Retained the legacy selector when present.
- Added current channel surfaces and message selectors as fallbacks.
- When a message is visible, walks up its DOM ancestors to find the actual
  vertically scrollable container instead of assuming its `data-tid`.
- Increased the surface wait to 30 seconds and added a browser-backed regression
  test for the scroll-parent fallback.

Limit:

Teams DOM is not a public stable API. This adapter still requires production
capture evidence after future Teams UI changes.

### 8. Chrome closed during capture and every remaining channel failed

Observed error:

```text
Target page, context or browser has been closed
```

Evidence:

- The local FastAPI process remained alive.
- The Playwright-managed Chrome processes were gone.
- Windows Application, Defender, and Code Integrity logs did not record a Chrome
  crash or policy block at the observed time.

Repository fix:

- Each channel now obtains the current page instead of retaining one stale page
  for the entire queue.
- A target-closed error resets Playwright, reopens the persistent Chrome profile,
  and retries the affected channel once.
- Opening Chrome now disposes stale Playwright/context/page objects before
  launching a replacement and cleans up a partially started driver on launch
  failure.
- Added a coordinator recovery test that closes the first attempt and verifies
  that the second attempt completes.

Limit:

The supplied logs prove loss of the browser target, not what closed it. Recovery
is implemented, but the initiating cause remains unproven.

### 9. `/api/status` returned 500 while Chrome was closing

Observed traceback:

```text
teams_archive/capture/browser.py, in status
playwright._impl._errors.TargetClosedError:
Target page, context or browser has been closed
```

Cause:

`status()` checked `page.is_closed()` and then awaited DOM queries. The page
could close between those operations while the frontend polled once per second.

Repository fix:

- Status reads use a captured page reference.
- A target-closed race returns the normal disconnected Chrome state instead of
  an ASGI exception.
- Unrelated Playwright errors are still raised rather than hidden.
- Status never resets a shared session because capture recovery may already own
  a newer page.
- Added positive and negative tests for the race boundary.

### 10. Console build experiment and browser lifetime

A console PyInstaller build was tested to expose runtime logs. One intermediate
console hash was allowed by Smart App Control, but the next console hash was
blocked. The repository therefore keeps the normal windowed executable; console
mode is not a reliable trust workaround. Application shutdown closes the
Playwright-managed Chrome context by design.

### 11. A large thread failed after smaller threads completed

Observed behavior:

```text
IntegrityError: FOREIGN KEY constraint failed
```

Cause:

- The affected root had 281 replies and Teams loaded the history in overlapping
  virtualized batches.
- The old implementation kept only the final DOM batch after 16 load rounds.
  That batch did not contain the root post, so the first visible reply was
  treated as the root and later replies referenced a root row that did not
  exist.
- Four deleted-message tombstones had no message ID, author, timestamp, or body;
  the old fallback key collapsed all four into one item.

Repository fix:

- Merge messages from every rendered reply batch by stable source identity.
- Capture the canonical root before opening its reply pane and always persist it
  first.
- Give ID-less tombstones a positional capture key based on adjacent message IDs
  and replace stale synthetic tombstones after a count-matching rerun.
- Keep loading a known-size thread until the displayed reply count is reached or
  the bounded 80-round limit is exhausted.
- Added database regressions for canonical roots and synthetic-tombstone
  idempotency.

Production evidence on the same channel: 5 root posts and 396/396 replies were
committed with zero foreign-key violations.

### 12. A detached attachment card failed the whole channel

Observed behavior:

```text
TimeoutError while evaluating ... nth(18)
```

Cause:

Teams re-rendered its virtualized attachment list after earlier downloads. A
later index disappeared before metadata extraction, and that extraction was
outside the per-file error boundary.

Repository fix:

- Traverse the current attachment buttons in reverse order.
- Bound metadata reads to five seconds.
- Contain the complete metadata/menu/download operation per item so a detached
  card is reported as a failed attachment instead of failing the channel.
- Only recognize source URLs inside a Teams file-attachment grid; ordinary
  links and URL previews are no longer treated as files.

Follow-up fix:

Attachment capture now runs inside each rendered batch and performs a bounded
top-to-bottom sweep after the thread is loaded. Pending references are reported
separately from attempted failures.

### 13. SharePoint links returned HTML instead of file bytes

Observed error:

```text
source-returned-html
```

Cause:

Some rendered SharePoint document URLs start a download when navigated by
Chrome, but the same URL returns an HTML preview through request context, even
with `download=1`.

Repository fix:

- Keep the Teams menu action as the first choice.
- Support legacy file cards whose menu button has an empty accessible name.
- If the card cannot be driven, open the rendered HTTPS SharePoint URL in a
  temporary Chrome page and capture its browser download event.
- Retain `download=1` request context only as a final fallback; reject HTML,
  empty responses, non-HTTPS URLs, and non-SharePoint hosts.
- Persist downloaded files immediately at deterministic paths so restart and
  rerun reuse them without redownloading.

Linux production evidence across three channels: 10/10 roots, 587/587 replies,
151/151 attachment references, 18/18 hosted images, zero failed/pending files,
and every local path non-empty.

### 14. Chrome crash followed by `channel-not-visible` in 0.3.0

The Windows 0.3.0 run recorded its first thread (one root and 34/34 replies),
then the main Chrome process crashed. Two crash dumps reported `0xE0000008`
and an attempted allocation of `0xFFFFFFFFFFFFFFF4` while approximately
5.7–6.2 GiB remained available. This is not evidence that the machine ran out
of RAM.

The two raw dumps were stackwalked locally and their Chrome addresses mapped
with the public PDB for Chrome 152.0.7977.84. The frames were recovered by
stack scanning, so the exact unwind cannot be guaranteed, but both show the
same coherent chain on `CrBrowserMain`:
`DownloadBubbleUpdateService::CacheManager::UpdateDisplayInfoForDownloadItem`
→ `DownloadItemImpl::AddObserver` →
`vector<CheckedObserverAdapter>::emplace_back` →
`PartitionExcessiveAllocationSize`. Chrome's crash breadcrumbs end with a
`Tab2` navigation marked `#download ERR_ABORTED` in both dumps. The immediate
failure is therefore in Chrome's download-item UI path. The breadcrumbs do not
prove which app action or SharePoint response initiated that download, and the
precise memory corruption or arithmetic error inside Chrome is still unknown.
The earlier Linux capture used Chrome 149, while this Windows run used Chrome
152; these observations do not isolate the operating system as the cause.

After reopening Chrome, the app started at Teams home and immediately searched
for each channel before Teams had finished loading. It also ignored the saved
channel URL. Both channels then failed with `channel-not-visible`. This is a
separate app recovery failure, not an explanation for the Chrome crash. The six
files shown for the first channel had already been saved in an earlier run; the
0.3.0 run did not finish that channel.

Recovery change in 0.3.1:

- Navigate to a saved HTTPS Teams channel URL when available, and verify the
  channel name, Team, and observable source ID before capture.
- If no usable URL exists, wait for the Teams layout before using the channel
  tree or search UI. Reject stored URLs outside the known Teams hosts.
- Preserve per-post checkpoints so a retry can skip the already saved thread.
- On Windows, stream file responses from rendered HTTPS SharePoint URLs through
  the managed Chrome session using DevTools Fetch. This captures the bytes
  before Chrome creates a download item, avoiding the observed download-bubble
  stack. A failed stream falls back only to a request-context fetch; it is
  reported as incomplete if no valid bytes are available. It does not invoke
  Chrome's download-item UI again during that file attempt.

The Chrome internal defect remains outside the app. A headed Chrome test with a
synthetic HTML preview and file response captured all bytes without a download
event. The 0.3.1 mitigation needs a real Windows capture before claiming it
prevents the crash there or preserves full file coverage.

## Validation performed

The 0.3.1 Linux source test run reported:

```text
32 passed
```

Earlier checks on the same change series also passed:

- 3 frontend Vitest tests.
- ESLint.
- TypeScript and Vite production build.
- PyInstaller Windows onedir build.
- Packaged `--self-test` for Playwright.
- Packaged local `/api/health` response.
- A Mark-of-the-Web simulation for an intermediate build, with no corresponding
  Code Integrity block event.

The 0.3.1 Linux PyInstaller package passed `--self-test`. A previous unsigned
Windows diagnostic hash was blocked by Smart App Control; the Windows 0.3.1
package still needs GitHub Actions build and real Teams capture validation.

These checks cover regressions and packaging. They do not replace the remaining
production acceptance test.

## Required production acceptance test

Do not call the Windows release verified until one selected channel completes
with all of the following evidence:

1. The run and channel statuses are `completed`, not `partial` or `failed`.
2. The number of root posts processed equals the number encountered while
   scrolling the channel to its oldest reachable post.
3. Every opened thread has matching expected and captured reply counts.
4. Every visible attachment is either downloaded with status `local` or is
   explicitly reported as a failed attachment; a `completed` run has zero failed
   attachments.
5. Every stored attachment path exists under the configured `files` root and
   the file is non-empty.
6. The archive UI can open at least one stored post and one stored attachment
   after Chrome is closed.
7. Restarting or retrying does not duplicate messages or attachment rows.

## User runbook

1. End every older `Teams Offline Archive.exe` process before changing builds.
2. Extract the artifact into a new directory; do not run it from inside the ZIP.
3. Run `Teams Offline Archive.exe`.
4. Use the Chrome window opened by the app and sign in to Teams there.
5. Keep that managed Chrome window open during capture.
6. If a channel fails, use its **Retry** button after the current run finishes.
7. Preserve the console traceback when reporting a failure.

## Intermediate artifacts

Local diagnostic artifacts were named `fixed`, `fixed-v2`, `fixed-v3`,
`fixed-v4`, and `fixed-v5-console`. Only a future artifact built from a commit
that passes the production acceptance test should be presented as the verified
release.
