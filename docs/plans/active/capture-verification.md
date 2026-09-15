# Complete channel capture verification

Status: Active

## Authority and outcome

User explicitly requests repair and verification of one complete real Teams channel before delivery. Follow docs/ARCHITECTURE.md: rendered DOM only, no Teams writes, credentials stay in Chrome, sequential capture, durable per-post checkpoints.

## Approach

Inspect live UI and correlate errors before changes. Reproduce with existing selected channel. Repair lifecycle and capture failures with regression tests. Verify source counts, saved messages/replies, all attachments and local readability, then packaged application behavior. Do not equate synthetic tests or self-test with complete capture.

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
- A fresh production run completed all 5 roots with 396/396 displayed replies,
  31 downloaded files, zero foreign-key violations, and zero duplicate primary
  keys. The run remains `partial` because 127 attachment references were not
  downloaded; complete attachment traversal across virtualized batches remains
  unverified.
- Backend regression suite now has 19 passing tests.
- Windows troubleshooting and the complete fix history are recorded in
  `docs/windows-troubleshooting.md`.
