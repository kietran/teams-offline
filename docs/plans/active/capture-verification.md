# Complete channel capture verification

Status: Active

## Authority and outcome

User explicitly requests repair and verification of 2–3 complete real Teams
channels before delivery, including every rendered root, reply, image, and
downloadable file. Follow docs/ARCHITECTURE.md: rendered DOM only, no Teams
writes, credentials stay in Chrome, sequential capture, durable per-post and
per-file checkpoints.

## Approach

Download attachments while each virtualized batch is still rendered, persist
per-file outcomes across overlapping batches and reruns, and keep message
capture independent from file failures. Verify the large existing channel plus
1–2 additional channels with different reply/file shapes. Compare displayed
counts, unique file references, successful non-empty local files, archive
opening, and idempotent reruns. Do not equate synthetic tests or self-test with
complete capture.

## Recovery

Preserve existing archive/profile. Stop only identified app processes during an idle controlled restart. No security policy changes. Keep existing artifacts until replacement is verified.

## Progress

- Status endpoint close race fixed locally; 16 tests pass.
- Reproduced the Windows-reported failure on the selected 00728 channel: the
  first three roots completed, then a 281-reply virtualized thread omitted its
  root from the final DOM batch and caused a SQLite foreign-key failure.
- Capture now merges every virtualized reply batch, preserves the canonical
  root identity, distinguishes four ID-less tombstones, and contains detached
  attachment-card failures per file instead of failing the channel.
- Attachment capture now runs while each virtualized batch is rendered, sweeps
  the loaded thread, supports both named and legacy unlabeled menu buttons, and
  falls back to a Chrome navigation download for rendered SharePoint URLs that
  return HTML through request context.
- Production verification completed on three channels: 10/10 roots, 587/587
  displayed replies, 151/151 attachment references, and 18/18 hosted images.
  Every recorded local path exists and is non-empty; all three channel runs are
  `completed` with zero failed and zero pending files.
- Recovery was exercised mid-thread: 63 durable files were reused after restart
  and progress counters remained intact. A subsequent rerun kept the database
  stable at 599 messages and 214 attachment rows.
- Foreign-key checks and duplicate message/attachment primary-key checks report
  zero violations. Backend regression suite now has 26 passing tests.
- Windows troubleshooting and the complete fix history are recorded in
  `docs/windows-troubleshooting.md`.
- Windows 0.3.0 crashed Chrome after the first thread. Both dumps have the same
  symbolized Chrome download-bubble stack ending in an excessive allocation;
  the exact app action that triggered it remains unknown. The app then lost the
  channel on reopen and failed both channels with `channel-not-visible`.
- The 0.3.1 recovery change uses the saved Teams URL when present and waits for
  Teams to load before UI navigation. Windows file capture now streams
  SharePoint responses through Chrome DevTools Fetch without creating a Chrome
  download item; invalid or unavailable files remain reported as incomplete.
  Synthetic headed Chrome streaming proof and Linux regression tests pass.
  Windows production verification remains open.
