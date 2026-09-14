# MVP User Stories — Chrome Channel Capture

Date: 2026-09-14

Status: Accepted for MVP implementation.

## P0 — US-01: Connect Chrome without technical setup

As a low-tech user, I want the app to open Chrome and guide me to sign in to
Teams so I can begin without Microsoft admin, Graph, or command-line setup.

Acceptance criteria:

- One primary action: `Mở Chrome`.
- Credentials and MFA stay inside Chrome.
- Success is shown as icon plus `Chrome đã kết nối`.
- Expired sessions pause safely and offer `Đăng nhập lại`.

## P0 — US-02: Select a small set of channels

As a user, I want to open a channel in Chrome and add it to the app so I can
choose only the 5–10 channels I care about.

Acceptance criteria:

- One primary action: `Thêm kênh đang mở`.
- Selected channels are grouped by Team and show `Sẵn sàng`.
- Duplicate selection does not create a duplicate row.
- The user can remove or change the list before capture.

## P0 — US-03: Capture a complete visible channel with resume

As a user, I want one button to save every visible post, reply, image, and
downloadable file from my selected channels so I do not repeat manual work.

Acceptance criteria:

- One idle action: `Bắt đầu lưu`; one running action: `Tạm dừng`.
- The app harvests virtualized post/reply batches and records a durable
  checkpoint after each completed post.
- Restart resumes without duplicating completed content.
- File/channel failures stay isolated and expose `Thử lại`.
- The report states captured counts and uncertainty; it never silently claims
  completeness.

## P0 — US-04: Understand progress without technical logs

As a user, I want to know which channel is running and whether I need to act.

Acceptance criteria:

- Show `Đang lưu kênh {current}/{total}`, current channel, one progress bar,
  and contextual post/reply/file counts.
- Channel rows use `Đã lưu`, `Đang lưu`, `Đang chờ`, or `Cần thử lại`.
- Closing Chrome or losing login explains the single recovery action.
- Technical diagnostics are secondary and do not replace plain-language copy.

## P0 — US-05: Search and read offline

As a user, I want to search saved posts and open their full reply threads so I
can retrieve information without Teams.

Acceptance criteria:

- A single search field searches posts and replies.
- Results show channel, author, date, excerpt, and file count.
- The detail view shows root post, attachments, and chronological replies.
- Captured text and embedded images remain readable offline.
- `Mở tệp` opens the local file first, then the Drive copy when needed.

## Cross-Story Visual Acceptance

- Modern minimal desktop UI; no dashboard, charts, decorative cards, gradients,
  unnecessary animation, or technical configuration on primary screens.
- One primary action per screen, 44px controls, visible focus, 4.5:1 contrast,
  and icon-plus-text statuses.
- Windows and Linux share the same layout and Google Chrome workflow.
- Long channel names, loading, empty, paused, success, partial-success, offline,
  and error states remain understandable without horizontal overflow.
