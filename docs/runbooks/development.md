# Development Runbook

## Prerequisites

- Python 3.12+
- Node.js 24 LTS recommended
- Google Chrome Stable
- `uv`, npm, and `zstd` for Linux packaging

## Install And Run

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
npm --prefix frontend install
npm --prefix frontend run build
TEAMS_ARCHIVE_DATA_DIR=/tmp/teams-offline-archive-dev .venv/bin/python -m teams_archive.main
```

The service listens only on `http://127.0.0.1:8765`. Set
`TEAMS_ARCHIVE_NO_OPEN=1` for package/API smoke tests that must not open the
default browser.

## Validation

```bash
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
scripts/bin/harness doctor
```

## Packages

```bash
scripts/build-linux.sh
```

On Windows PowerShell:

```powershell
scripts\build-windows.ps1
```

Build each package on its target OS. Do not commit real Chrome profiles,
captures, downloaded files, screenshots, cookies or tokens.
