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
- Full real capture remains unverified. Existing app reports channel-not-visible after browser recovery.
- Earlier viewport-removal claim was not established by live DOM evidence.
- Windows troubleshooting and the complete fix history are recorded in
  `docs/windows-troubleshooting.md`.
