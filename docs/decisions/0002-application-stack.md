# 0002 Application Stack And Local Runtime

Date: 2026-09-12

## Status

Accepted

## Context

Ứng dụng cần UI desktop hiện đại, local search nhanh, visible Chrome capture và
bản portable không yêu cầu người dùng cài môi trường phát triển.

## Decision

- React + Vite + TypeScript cho frontend.
- Python + FastAPI cho local service và Playwright Chrome capture.
- sqlite3 + FTS5 cho archive/search.
- PyInstaller `onedir`: ZIP portable trên Windows và `tar.zst` trên Linux.

## Alternatives Considered

1. Electron: bundle lớn hơn mức cần thiết cho ứng dụng cá nhân.
2. Tauri: packaging gọn nhưng tăng số runtime/toolchain cần duy trì.
3. Native UI riêng từng OS: tăng số codebase và làm chậm capture/search.

## Consequences

Positive:

- Tách UI và connector rõ, dễ kiểm thử.
- SQLite chạy hoàn toàn local và FTS5 phù hợp search archive.
- Cùng frontend và archive format chạy trên Linux/Windows.

Tradeoffs:

- Mỗi OS phải build gói riêng trên chính OS đó.
- Local HTTP service cần giữ invariant loopback-only.

## Follow-Up

- Xác minh gói Windows trên Windows x64; Linux đã build/smoke trên EndeavourOS.
