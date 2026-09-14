# UI/UX Specification — Chrome Channel Capture

Date: 2026-09-14

Status: Accepted design direction; implementation not started.

## Experience Goal

Teams Offline Archive is a personal desktop tool for one low-tech user. It has
two jobs only:

1. Save all visible content from 5–10 selected Teams channels through Chrome.
2. Find and read the saved content without opening Teams.

The UI must hide browser automation, DOM extraction, retries, checkpoints, and
SQLite. It must never resemble an admin dashboard.

## UI UX Pro Max Application

Two design-system searches were rejected because they returned marketing
landing-page patterns. The verified guidance applied here is:

- modern minimalism / Swiss functional layout;
- one primary action per screen;
- progress with clear context and recovery actions;
- open lists with dividers instead of metric cards;
- visible focus, semantic status text, and keyboard operation;
- stable layout during loading and long-running capture;
- reduced motion and no decorative animation.

Design dials: variance 3/10, motion 2/10, density 5/10.

## Visual System

- Canvas: `#F8FAFC`; content surface: `#FFFFFF`.
- Primary text: `#1E293B`; secondary text: `#64748B`.
- Dividers: `#E2E8F0`; primary/action: `#2563EB`.
- Success: `#15803D`; warning: `#B45309`; destructive: `#B91C1C`.
- Selected row: `#EFF6FF`.
- Font stack: `system-ui, "Segoe UI", "Noto Sans", sans-serif`; no remote font.
- Type scale: 14, 16, 18, 24, 32px. Body copy is 16px with 1.5 line-height.
- Radius: 8px controls and panels. Lists use dividers, not repeated cards.
- Lucide outline icons only; icons beside visible labels are decorative.
- Motion: 150–200ms opacity/color transitions; progress movement may be linear.
- No dark mode in the initial release.

## Information Architecture

After setup, the app has exactly two primary destinations:

1. `Sao lưu`
2. `Kho lưu trữ`

Settings and technical logs stay behind a secondary overflow/help entry and do
not occupy primary navigation.

## First-Run Setup

Use a three-step wizard:

1. `Kết nối Chrome`
2. `Chọn kênh`
3. `Nơi lưu`

### Step 1 — Kết nối Chrome

- Heading: `Mở Teams trong Chrome`.
- Explain that the user signs in directly in Chrome and may complete MFA.
- Primary action: `Mở Chrome`.
- Success state: `Chrome đã kết nối` plus a check icon.
- Do not mention OAuth, Graph, tenant, admin consent, cookies, or browser profile.

### Step 2 — Chọn kênh

- Heading: `Chọn kênh cần lưu`.
- Helper: `Thêm khoảng 5–10 kênh bạn muốn lưu để xem lại khi cần.`
- Show three short instructions:
  1. `Mở Teams trong Chrome`.
  2. `Mở kênh cần lưu`.
  3. `Bấm Thêm kênh đang mở`.
- Primary action: `Thêm kênh đang mở`.
- Selected channels appear as an open list grouped by Team.
- Each row shows channel name, `Sẵn sàng`, and the text action `Xóa`.
- Duplicate channels are ignored with the message `Kênh này đã được thêm`.
- Empty state keeps the instruction panel visible; it does not use an
  illustration or extra CTA.

Concept: `docs/design/concepts/channel-capture-selection.png`.

### Step 3 — Nơi lưu

- Confirm the local archive location in human language.
- Primary action: `Hoàn tất thiết lập`.
- Offer `Mở thư mục` as a secondary action.
- Do not show a technical path picker in the initial release.

## Sao lưu Screen

### Idle

- Heading: `Sao lưu từ Teams`.
- Show selected channel rows and the last saved time.
- One primary action: `Bắt đầu lưu`.
- Secondary text action: `Thay đổi kênh`.
- If Chrome is signed out, replace the primary action with `Đăng nhập lại`.

### Running

- Context line: `Đang lưu kênh {current}/{total}`.
- Show current channel, one overall progress bar, and contextual counts:
  `{postsDone}/{postsSeen} bài viết · {replies} bình luận · {files} tệp`.
- Channel rows use these text-plus-icon states:
  `Đã lưu`, `Đang lưu`, `Đang chờ`, `Cần thử lại`.
- Only the active operation action is shown: `Tạm dừng`.
- The user may navigate to `Kho lưu trữ` while capture continues.
- A persistent info strip says:
  `Bạn có thể đóng ứng dụng. Lần sau quá trình sẽ tiếp tục từ đây.`

Concept: `docs/design/concepts/channel-capture-progress.png`.

### Completion

- Heading: `Đã lưu xong`.
- Summary sentence, not metric cards:
  `Đã lưu {channels} kênh, {posts} bài viết, {replies} bình luận và {files} tệp.`
- Primary action: `Mở kho lưu trữ`.
- If failures exist, use `Đã lưu phần lớn nội dung` and place `Thử lại` directly
  on each failed channel/file row.

## Kho lưu trữ Screen

- Preserve a three-pane desktop reader:
  - left: selected Team/channel tree;
  - middle: search and post results;
  - right: root post, attachments, and chronological replies.
- Top navigation contains `Sao lưu` and `Kho lưu trữ`; no API update button.
- Search placeholder: `Tìm trong bài viết và bình luận...`.
- Search is immediate with a short debounce; `Esc` clears it.
- Attachment action is always labeled `Mở tệp`.
- Offline availability appears as `Có thể xem ngoại tuyến` with a check icon.
- No advanced filters, tags, notes, composer, edit action, dashboard, or charts.

Concept: `docs/design/concepts/archive-viewer-v2.png`.

## Error And Recovery Copy

Every error states what happened and what to do next.

- Chrome closed: `Chrome đã đóng — Mở lại Chrome để tiếp tục.`
- Teams signed out: `Phiên Teams đã hết hạn — Đăng nhập lại trong Chrome.`
- Channel unavailable: `Không mở được kênh này — kiểm tra quyền truy cập rồi thử lại.`
- Reply expansion uncertain: `Chưa thể xác nhận đã tải hết bình luận — mở kênh để kiểm tra.`
- File failed: `Không tải được tệp này — tệp có thể đã bị xóa hoặc giới hạn quyền.`
- Local storage full: `Ổ đĩa đã đầy — giải phóng dung lượng rồi thử lại.`

Errors are inline at the affected row. Technical details are behind `Chi tiết`
and never replace the recovery action.

## Accessibility And Interaction

- All primary controls are at least 44px high with at least 8px separation.
- Focus ring: 2px blue with 2px offset; tab order matches visual order.
- Status never relies on color alone; use icon plus full text.
- Progress updates use one atomic `role=status` message such as
  `Đã lưu 3 trong 8 kênh`; do not announce every numeric change.
- Progress bars expose a text label and current/min/max values.
- Long Team/channel names wrap or truncate with a keyboard-accessible tooltip.
- Loading placeholders reserve their final space to avoid layout shift.
- Lists over 50 rows are virtualized; capture work stays outside the UI thread.
- `prefers-reduced-motion` removes nonessential transitions.
- Sticky navigation must not obscure keyboard focus at 200% zoom.

## Responsive Desktop Behavior

- Primary targets: 1280×720, 1440×900, and 1920×1080.
- At 1024–1279px, reduce pane widths while preserving the detail pane.
- Below 1024px, archive results use master-detail; setup/progress remain one
  column. There is no mobile application requirement.
- Windows and Linux share the same layout and Chrome-based workflow.

## Explicit Non-Goals

- No Microsoft admin/Graph/RSC setup UI.
- No automatic tenant-wide Team discovery.
- No scheduled or background capture while the user is logged out.
- No analytics, charts, collaboration, sharing, tagging, notes, or editing.
- No claim of compliance-grade completeness.
- No browser extension in the initial release.
