import pytest

from teams_archive.capture.models import ChannelIdentity
from teams_archive.capture.service import CaptureCoordinator
from teams_archive.db import ArchiveDatabase


class RecoveringBrowser:
    def __init__(self) -> None:
        self.reopen_calls = 0

    async def page(self):
        return object()

    async def reopen(self):
        self.reopen_calls += 1

    async def close(self):
        return None


class ClosingOnceExtractor:
    def __init__(self) -> None:
        self.attempts = 0

    async def navigate_to_channel(self, _page, _team_name, _channel_name):
        return None

    async def discover_current_channel(self, _page):
        return ChannelIdentity("ui-channel:one", "ui-team:one", "Client", "Legal", "source", "source_id")

    async def capture_channel(self, _page, _identity, _completed, _on_post, _pause_gate):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("Target page, context or browser has been closed")
        return {"posts": 0, "expectedReplies": 0, "capturedReplies": 0, "files": 0, "failedFiles": 0, "uncertain": 0}


@pytest.mark.asyncio
async def test_capture_reopens_chrome_and_retries_channel_once(tmp_path) -> None:
    database = ArchiveDatabase(tmp_path / "archive.db")
    database.initialize()
    database.upsert_channel({
        "id": "ui-channel:one", "teamId": "ui-team:one", "teamName": "Client",
        "displayName": "Legal", "membershipType": "standard", "webUrl": None,
        "sourceLocator": "source", "identityConfidence": "source_id",
    })
    browser = RecoveringBrowser()
    extractor = ClosingOnceExtractor()
    coordinator = CaptureCoordinator(database, browser, extractor)

    await coordinator.start(["ui-channel:one"])
    await coordinator._task

    assert browser.reopen_calls == 1
    assert extractor.attempts == 2
    assert database.current_capture()["status"] == "completed"
