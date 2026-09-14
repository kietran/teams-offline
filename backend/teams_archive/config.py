from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


APP_NAME = "Teams Offline Archive"
APP_SLUG = "TeamsOfflineArchive"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    assets: Path
    staging: Path
    offline_cache: Path
    logs: Path
    reports: Path
    files: Path
    chrome_profile: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        configured = os.getenv("TEAMS_ARCHIVE_DATA_DIR", "").strip()
        root = Path(configured).expanduser() if configured else Path(user_data_path(APP_SLUG, appauthor=False))
        return cls(
            root=root,
            database=root / "archive.db",
            assets=root / "assets",
            staging=root / "staging",
            offline_cache=root / "offline-cache",
            logs=root / "logs",
            reports=root / "reports",
            files=root / "files",
            chrome_profile=root / "chrome-profile",
        )

    def ensure(self) -> None:
        for path in (
            self.root, self.assets, self.staging, self.offline_cache,
            self.logs, self.reports, self.files, self.chrome_profile,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    paths: AppPaths

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(paths=AppPaths.discover())
