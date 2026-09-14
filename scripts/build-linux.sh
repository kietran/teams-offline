#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
npm --prefix frontend run build
.venv/bin/pyinstaller --noconfirm --clean packaging/teams_offline_archive.spec
cp README.md "dist/Teams Offline Archive/README.md"
tar --zstd -cf "dist/TeamsOfflineArchive-linux-x86_64.tar.zst" -C dist "Teams Offline Archive"
echo "dist/TeamsOfflineArchive-linux-x86_64.tar.zst"
