# 0001 App-Managed Google Drive Root Folder

Date: 2026-09-11

## Status

Deferred by the local-first MVP decision on 2026-09-14. Retained as a future
storage option; it is not implemented or exposed in the current runtime.

## Context

Người dùng ít kinh nghiệm kỹ thuật cần kết nối Google Drive để lưu file lớn.
Yêu cầu chọn một đường dẫn Drive trong wizard làm tăng thao tác, nguy cơ chọn
nhầm và độ phức tạp về quyền truy cập.

## Decision

Trong MVP, ứng dụng tự tạo và ghi nhớ folder ID của
`My Drive/Teams Offline Archive`. Wizard không có path picker.

## Alternatives Considered

1. Bắt buộc chọn thư mục mỗi lần thiết lập.
2. Tạo thư mục mặc định nhưng cho đổi path ngay trong wizard.
3. Cho chọn lại thư mục trong phần advanced settings.

## Consequences

Positive:

- Setup ngắn hơn và ít lỗi hơn.
- Ứng dụng có thể giới hạn quyền và quản lý đúng những tệp nó tạo.
- Folder ID ổn định ngay cả khi người dùng đổi tên hoặc di chuyển thư mục.

Tradeoffs:

- Người dùng không chọn được cấu trúc Drive tùy ý trong MVP.
- Nếu thư mục bị đưa vào trash/xóa, ứng dụng cần một recovery flow đơn giản.

## Follow-Up

- Thiết kế hành vi khi folder bị trash hoặc không còn quyền truy cập.
- Chỉ thêm custom folder nếu có nhu cầu thực tế sau MVP.
