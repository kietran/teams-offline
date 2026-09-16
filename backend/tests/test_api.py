from pathlib import Path

import httpx
import pytest

from teams_archive.api import create_app
from teams_archive.capture.models import ChannelIdentity, ChromeState
from teams_archive.config import AppConfig, AppPaths


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(AppPaths(tmp_path, tmp_path/"archive.db", tmp_path/"assets", tmp_path/"staging", tmp_path/"offline-cache", tmp_path/"logs", tmp_path/"reports", tmp_path/"files", tmp_path/"chrome-profile"))


class FakeExtractor:
    async def discover_current_channel(self, _page):
        return ChannelIdentity("channel-1", "team-1", "Client", "Legal", "source", "source_id")


class FakeBrowser:
    def __init__(self): self.state = ChromeState(True, False, False, False)
    async def status(self): return self.state
    async def open(self): self.state = ChromeState(True, True, True, False, {"displayName":"Legal"}); return self.state
    async def page(self): return object()


class FakeCoordinator:
    def __init__(self, db): self.database=db; self.extractor=FakeExtractor(); self.active=False
    async def start(self, ids=None): self.active=True; return self.database.create_capture_run(ids or ["channel-1"])
    async def pause(self, _id): return None
    async def resume(self, _id): return None
    async def shutdown(self): return None


@pytest.mark.asyncio
async def test_setup_channel_and_capture_api(tmp_path: Path) -> None:
    config=make_config(tmp_path); browser=FakeBrowser()
    from teams_archive.db import ArchiveDatabase
    db=ArchiveDatabase(config.paths.database); db.initialize(); coordinator=FakeCoordinator(db)
    app=create_app(config, browser, coordinator)
    transport=httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/health")).json()["version"] == "0.3.2"
        assert (await client.post("/api/chrome/open")).json()["signed_in"] is True
        added=(await client.post("/api/channels/current")).json()
        assert added["display_name"] == "Legal"
        assert (await client.post("/api/setup/complete")).json()["setupComplete"] is True
        response=await client.post("/api/captures", json={})
        assert response.status_code == 202
        assert (await client.post("/api/captures", json={})).status_code == 409
