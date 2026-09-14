# Page Override: Channel Capture Progress

This page overrides the generated Master where rules conflict.

- Navigation: two labeled destinations only, `Sao lưu` and `Kho lưu trữ`.
- Layout: page heading, one overall progress surface, and one channel status list.
- Progress copy names the current channel and `{current}/{total}` channel count.
- Channel states: icon plus `Đã lưu`, `Đang lưu`, `Đang chờ`, or `Cần thử lại`.
- Recovery actions sit on the affected row; technical detail is secondary.
- Running action: `Tạm dừng`. Idle action: `Bắt đầu lưu`.
- Keep the archive usable while capture runs.
- Forbidden: metric cards, charts, raw logs, multiple progress graphs, animated
  celebration, or more than one primary action.
- Concept: `docs/design/concepts/channel-capture-progress.png`.
