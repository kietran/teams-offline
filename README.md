# Teams Offline Archive

Ứng dụng local cho Windows và Linux, dùng Google Chrome Stable để lưu nội dung
hiển thị từ 5–10 Microsoft Teams channels mà không cần Graph hoặc admin consent.

## Trạng thái

Local Chrome Capture MVP đã có:

- Chrome session/profile riêng.
- Thêm channel đang mở.
- Capture queue, pause/resume và checkpoint SQLite.
- Lưu root posts, replies, ảnh và file đính kèm trong posts.
- Full-text search và archive viewer.
- Linux portable build; Windows build script chờ chạy trên Windows x64.

Google Drive và quét toàn bộ tab Shared được hoãn khỏi MVP.

## Phát triển

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
npm --prefix frontend install
npm --prefix frontend run build
TEAMS_ARCHIVE_DATA_DIR=/tmp/teams-offline-archive-dev .venv/bin/python -m teams_archive.main
```

Ứng dụng chỉ listen tại `http://127.0.0.1:8765`.

## Tải bản Windows từ GitHub Actions

Mở tab **Actions** của repository, chọn workflow **Build Windows**, mở run mới
nhất và tải artifact `TeamsOfflineArchive-windows-x64`. Giải nén artifact rồi
giải nén `TeamsOfflineArchive-windows-x64.zip`; chạy
`Teams Offline Archive/Teams Offline Archive.exe`.

## Kiểm tra

```bash
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
scripts/bin/harness doctor
```

Tài liệu chính: `docs/product/overview.md`, `docs/product/ux-spec.md`,
`docs/ARCHITECTURE.md` và `docs/plans/active/initial-product.md`.
