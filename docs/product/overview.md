# Product Requirements: Teams Offline Archive

Date: 2026-09-14

## Status

Accepted for MVP implementation.

## Problem

The user needs a personal, searchable offline copy of all visible posts,
replies, embedded images, and downloadable files from approximately 5–10
Microsoft Teams channels. The user does not want a workflow that depends on a
Microsoft tenant administrator.

Observed channels typically contain 1–5 root posts, while an individual thread
may contain dozens of replies and attachments.

## Product Principle

This is a simple personal archive tool, not a Teams administration product.

- Optimize for one low-tech user and safe defaults.
- Show only familiar actions: open Chrome, add channel, start, pause, retry,
  search, and open file.
- Hide DOM extraction, browser profiles, checkpoints, SQLite, and checksums.
- Simple means few decisions and clear feedback, not dated visual quality.
- Do not add features merely because they are technically possible.

## Target Environment

- Windows x64 and Linux x86_64 from one codebase.
- Google Chrome Stable is the only supported browser in the MVP.
- Linux validation target: EndeavourOS with Hyprland/Wayland.
- One user; no accounts, roles, sharing, or collaboration inside the app.

## Product Shape

The product is a portable desktop application with a local React interface,
Python service, SQLite archive, and visible Chrome automation. Windows and Linux
use separate release packages but share the same archive format.

Chrome uses an application-owned persistent profile. The user enters Microsoft
credentials and completes MFA directly in Chrome. The application must not ask
for the Microsoft password, extract bearer tokens, or call undocumented Teams
APIs.

## Confirmed MVP Scope

### Setup and channel selection

- First run has three steps: `Kết nối Chrome`, `Chọn kênh`, and `Nơi lưu`.
- The app opens Chrome and waits for the user to sign in to Teams.
- To add a channel, the user opens it in the controlled Chrome window and clicks
  `Thêm kênh đang mở` in the app.
- The selected list targets approximately 5–10 channels and can be edited later.
- The initial release confirms one local storage folder; Google Drive is deferred.

### Channel capture

- For every selected channel, capture all visible root posts from newest to the
  oldest content Teams makes available in the UI.
- Open each thread and capture all visible replies in chronological order.
- Capture author, timestamps, rich text, links, mentions, embedded images,
  attachment metadata, and downloadable files.
- Download only files referenced by a captured root post or reply. The Shared
  tab is not scanned in the initial release.
- Harvest visible DOM batches before scrolling because Teams can virtualize long
  lists. Dedupe by source identifier when visible, otherwise by stable content
  hash.
- Save a durable checkpoint after each completed post. Pause, app close, browser
  close, network failure, or MFA expiry must not discard completed work.
- Retry only failed channels/files and never duplicate completed content.
- Capture is manual. No scheduled or unattended capture is in the MVP.

### Completeness contract

- This is a best-effort personal archive, not a compliance-grade export.
- The app may only capture content the signed-in user can render or download.
- A run report shows channels, posts, replies, images, files, failures, oldest
  visible timestamp, and newest timestamp.
- Compare UI-displayed counts when available. Otherwise stop after stable passes
  and require user confirmation rather than claiming 100% completeness.
- Deleted, access-restricted, or non-rendered content is explicitly out of reach.

### Archive and search

- Store posts/replies in SQLite with FTS5 full-text search.
- Keep embedded assets needed for offline reading locally.
- Store captured files locally and record the final state per file.
- Browse by Team/channel; search post and reply text; open a result as one root
  post with chronological replies.
- Open a captured local file with the operating system default application.
- Reading the archive never opens or calls Teams.

## Information Architecture

After setup, primary navigation has exactly two destinations:

1. `Sao lưu`
2. `Kho lưu trữ`

Technical logs and help are secondary and hidden from the normal workflow.

## Storage Layout

```text
Teams Offline Archive/
├── data/archive.db
├── data/assets/
├── data/files/
├── data/chrome-profile/
├── reports/
└── logs/
```

The archive database, assets, and reports are portable between Windows and
Linux. Browser profile data is platform-local and must not be copied as part of
an archive transfer.

## UX Requirements

- Modern, bright, calm desktop UI with system typography and restrained blue.
- One primary action per screen.
- Open lists with dividers rather than dashboard cards.
- Progress names the current channel and explains that the app can resume.
- Status uses icon plus text: `Đã lưu`, `Đang lưu`, `Đang chờ`, or
  `Cần thử lại`.
- Every error says what happened and what to do next.
- Search is a single prominent field; advanced filters are out of scope.
- Minimum 44px primary controls, visible keyboard focus, 4.5:1 text contrast,
  reduced-motion support, and no hidden action at 200% zoom.

Detailed contract: `docs/product/ux-spec.md`.

## Security And Privacy

- Bind the local service to loopback only.
- Never commit or log passwords, tokens, cookies, archive content, or Chrome
  profile data.
- Do not serialize browser authentication into a portable plaintext file.
- Use an application-owned browser profile protected by the current OS user.
- Do not modify, post, reply, edit, or delete anything in Teams.
- Do not publish or share the local archive/Drive folder automatically.

## Out Of Scope

- Microsoft Graph `ChannelMessage.Read.All`, RSC, Entra app registration, or an
  admin-consent setup flow.
- Browser extension.
- Tenant-wide discovery or backup of every Team/channel.
- Private chats, meeting chats, calls, calendars, Planner, Loop, Whiteboard, or
  third-party tabs.
- Compliance/legal completeness guarantee.
- Writing or restoring content to Teams.
- Scheduled capture, cloud-hosted viewer, multi-user access, collaboration,
  analytics, charts, tags, notes, or content editing.
- Dark mode or visual customization in the MVP.
- Google Drive upload and scanning all files in a channel's Shared tab.

## Success Criteria

- A low-tech user can connect Chrome and add a channel without technical input.
- A pilot captures every root post in one real channel (typically 1–5), verifies
  reply counts for every captured thread, and saves at least one embedded image
  and one downloaded file.
- Restart/resume continues from a durable checkpoint without duplicates.
- The user can search and read captured posts/replies with Teams closed.
- Windows and Linux packages use Chrome Stable and open the same archive data.
- Every partial or uncertain result is visible in the run report.
