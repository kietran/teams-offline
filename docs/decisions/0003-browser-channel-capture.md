# Decision 0003: Capture Selected Channels Through Chrome

Date: 2026-09-14

## Status

Accepted.

## Context

`ChannelMessage.Read.All` requires Microsoft tenant admin consent. The user does
not want an admin-dependent workflow and only needs approximately 5–10 selected
channels rather than tenant-wide backup.

## Decision

- Use Google Chrome Stable on Windows and Linux.
- Capture rendered Teams web content through visible browser automation.
- Use an application-owned persistent Chrome profile; the user signs in and
  completes MFA directly in Chrome.
- Do not extract bearer tokens, call undocumented Teams endpoints, or inject a
  browser extension in the initial release.
- Save all visible root posts, replies, embedded images, downloadable files,
  and a capture report for each selected channel.
- Treat completeness as best-effort and require count/error evidence plus a
  user confirmation step.

## Consequences

- No Microsoft Entra app registration or tenant admin consent is required.
- UI automation is more sensitive to Teams interface changes than Graph.
- Checkpointing and incremental DOM harvesting are mandatory because Teams may
  virtualize long lists.
- Windows and Linux need separate packaging and platform QA, but use the same
  browser workflow and archive format.
