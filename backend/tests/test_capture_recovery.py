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
        self.navigation_calls = []

    async def navigate_to_channel(self, _page, _team_name, _channel_name, web_url, source_locator):
        self.navigation_calls.append((web_url, source_locator))

    async def discover_current_channel(self, _page):
        return ChannelIdentity("ui-channel:one", "ui-team:one", "Client", "Legal", "source", "source_id")

    async def capture_channel(self, _page, _identity, _completed, _on_post, _pause_gate):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("Target page, context or browser has been closed")
        return {
            "posts": 0, "expectedReplies": 0, "capturedReplies": 0,
            "files": 0, "failedFiles": 0, "pendingFiles": 0, "uncertain": 0,
        }


class AddingPostExtractor(ClosingOnceExtractor):
    async def capture_channel(self, _page, _identity, completed, on_post, _pause_gate):
        assert completed == {"1000"}
        await on_post({
            "id": "2000", "expectedReplies": 1, "capturedReplies": 1, "countMatches": True,
            "messages": [
                {
                    "id": "2000", "text": "root", "html": "", "attachments": [{
                        "id": "file-2", "name": "two.pdf", "status": "local", "localPath": "/tmp/two.pdf",
                    }], "images": [],
                },
                {"id": "2001", "text": "reply", "html": "", "attachments": [], "images": []},
            ],
        })
        return {
            "posts": 1, "expectedReplies": 1, "capturedReplies": 1,
            "files": 1, "failedFiles": 0, "pendingFiles": 0, "uncertain": 0,
        }


class FailedFileExtractor(ClosingOnceExtractor):
    async def capture_channel(self, _page, _identity, _completed, on_post, _pause_gate):
        await on_post({
            "id": "1000", "expectedReplies": 0, "capturedReplies": 0, "countMatches": True,
            "messages": [{
                "id": "1000", "text": "root", "html": "", "images": [],
                "attachments": [{
                    "id": "file-1", "name": "report.pdf", "status": "failed",
                    "errorCode": "source-timeout", "localPath": None,
                }],
            }],
        })
        return {
            "posts": 1, "expectedReplies": 0, "capturedReplies": 0,
            "files": 0, "failedFiles": 1, "pendingFiles": 0, "uncertain": 0,
        }


@pytest.mark.asyncio
async def test_capture_reopens_chrome_and_retries_channel_once(tmp_path) -> None:
    database = ArchiveDatabase(tmp_path / "archive.db")
    database.initialize()
    database.upsert_channel({
        "id": "ui-channel:one", "teamId": "ui-team:one", "teamName": "Client",
        "displayName": "Legal", "membershipType": "standard",
        "webUrl": "https://teams.cloud.microsoft/v2/?channel=stored",
        "sourceLocator": "source", "identityConfidence": "source_id",
    })
    browser = RecoveringBrowser()
    extractor = ClosingOnceExtractor()
    coordinator = CaptureCoordinator(database, browser, extractor)

    await coordinator.start(["ui-channel:one"])
    await coordinator._task

    assert browser.reopen_calls == 1
    assert extractor.attempts == 2
    assert extractor.navigation_calls == [
        ("https://teams.cloud.microsoft/v2/?channel=stored", "source"),
    ] * 2
    assert database.current_capture()["status"] == "completed"


@pytest.mark.asyncio
async def test_resumed_channel_keeps_durable_progress_counters(tmp_path) -> None:
    database = ArchiveDatabase(tmp_path / "archive.db")
    database.initialize()
    channel = {
        "id": "ui-channel:one", "teamId": "ui-team:one", "teamName": "Client",
        "displayName": "Legal", "membershipType": "standard", "webUrl": None,
        "sourceLocator": "source", "identityConfidence": "source_id",
    }
    database.upsert_channel(channel)
    run_id = database.create_capture_run([channel["id"]])
    database.upsert_post(run_id, channel["id"], {
        "id": "1000", "expectedReplies": 2, "capturedReplies": 2, "countMatches": True,
        "messages": [
            {"id": "1000", "text": "root", "html": "", "attachments": [], "images": []},
            {"id": "1001", "text": "one", "html": "", "attachments": [], "images": []},
            {"id": "1002", "text": "two", "html": "", "attachments": [], "images": []},
        ],
    })
    database.update_channel_run(
        run_id, channel["id"], status="interrupted", posts_seen=1, posts_completed=1,
        expected_replies=2, captured_replies=2, files_captured=1, files_failed=1, files_pending=1,
    )
    coordinator = CaptureCoordinator(database, RecoveringBrowser(), AddingPostExtractor())

    result = await coordinator._capture_channel_once(run_id, channel["id"], database.get_channel(channel["id"]))

    assert result == {
        "posts": 2, "expectedReplies": 3, "capturedReplies": 3,
        "files": 2, "failedFiles": 1, "pendingFiles": 1, "uncertain": 0,
    }


@pytest.mark.asyncio
async def test_failed_file_keeps_post_and_marks_channel_partial(tmp_path) -> None:
    database = ArchiveDatabase(tmp_path / "archive.db")
    database.initialize()
    database.upsert_channel({
        "id": "ui-channel:one", "teamId": "ui-team:one", "teamName": "Client",
        "displayName": "Legal", "membershipType": "standard", "webUrl": None,
        "sourceLocator": "source", "identityConfidence": "source_id",
    })
    coordinator = CaptureCoordinator(database, RecoveringBrowser(), FailedFileExtractor())

    run_id = await coordinator.start(["ui-channel:one"])
    await coordinator._task

    progress = database.capture_channel_progress(run_id, "ui-channel:one")
    assert database.current_capture()["status"] == "partial"
    assert progress["status"] == "partial"
    assert progress["posts_completed"] == 1
    assert progress["files_failed"] == 1
    with database.connect() as connection:
        assert connection.execute("SELECT status FROM attachments WHERE id='file-1'").fetchone()[0] == "failed"
