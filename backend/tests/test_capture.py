from pathlib import Path

import pytest

from teams_archive.capture.extractor import (
    FORBIDDEN_ACTION_NAMES,
    TeamsDomExtractor,
    message_capture_key,
    safe_filename,
    stable_hash,
    storage_key,
    team_from_title,
)
from teams_archive.capture.service import sanitize_post


def test_capture_helpers_are_stable_and_cross_platform_safe() -> None:
    assert stable_hash("A", "B") == stable_hash("A", "B")
    assert storage_key("ui-channel:abc") == storage_key("ui-channel:abc")
    assert len(storage_key("ui-channel:abc")) == 32
    assert all(character in "0123456789abcdef" for character in storage_key("ui-channel:abc"))
    assert safe_filename('a<b>:c?.pdf') == "a_b__c_.pdf"
    assert team_from_title("Teams and Channels | Client | Legal | Microsoft Teams", "Legal") == "Client"


def test_message_html_is_sanitized_before_storage() -> None:
    captured = {
        "messages": [{
            "html": (
                '<p onclick="bad()">Safe<script>bad()</script>'
                '<a href="javascript:bad()">bad link</a>'
                '<a href="https://example.com" target="_blank">good link</a></p>'
            )
        }]
    }
    result = sanitize_post(captured)
    sanitized = result["messages"][0]["html"]
    assert "<script" not in sanitized
    assert "onclick" not in sanitized
    assert "javascript:" not in sanitized
    assert "Safe" in sanitized
    assert 'href="https://example.com"' in sanitized


def test_forbidden_write_actions_are_explicitly_owned() -> None:
    assert {"send", "share", "edit", "delete", "reply in thread"} <= FORBIDDEN_ACTION_NAMES


def test_virtualized_message_batches_have_stable_deduplication_keys() -> None:
    assert message_capture_key({"id": "123", "text": "first render"}) == message_capture_key(
        {"id": "123", "text": "updated render"}
    )
    assert message_capture_key({"id": None, "author": "A", "timestamp": "T", "text": "Body"}) == message_capture_key(
        {"id": None, "author": "A", "timestamp": "T", "text": "Body"}
    )
    assert message_capture_key({"id": None, "captureKey": "after:100:1"}) != message_capture_key(
        {"id": None, "captureKey": "after:100:2"}
    )


class MissingAttachmentCardPage:
    async def evaluate(self, _script, _argument):
        return False


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/pdf") -> None:
        self.ok = True
        self.status = 200
        self.headers = {
            "content-type": content_type,
            "content-disposition": "attachment; filename*=UTF-8''archive.pdf",
        }
        self._body = body

    async def body(self) -> bytes:
        return self._body


class FakeRequest:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def get(self, _url: str, timeout: int) -> FakeResponse:
        assert timeout == 30_000
        return self.response


class FakeWarmPage:
    async def goto(self, _url: str, wait_until: str, timeout: int) -> None:
        assert wait_until == "domcontentloaded"
        assert timeout == 30_000

    async def close(self) -> None:
        return None


class FakeContext:
    def __init__(self, request) -> None:
        self.request = request

    async def new_page(self) -> FakeWarmPage:
        return FakeWarmPage()


class DirectDownloadPage:
    def __init__(self, response: FakeResponse) -> None:
        self.context = FakeContext(FakeRequest(response))


class DownloadQueryRequest:
    async def get(self, url: str, timeout: int) -> FakeResponse:
        assert timeout == 30_000
        if "download=1" in url:
            return FakeResponse(b"forced-download")
        return FakeResponse(b"<html>preview</html>", "text/html")


class DownloadQueryPage:
    def __init__(self) -> None:
        self.context = FakeContext(DownloadQueryRequest())


class FakeNavigationDownload:
    suggested_filename = "navigation.pdf"

    async def save_as(self, path: str) -> None:
        Path(path).write_bytes(b"browser-download")


class FakeDownloadInfo:
    @property
    def value(self):
        async def resolve():
            return FakeNavigationDownload()
        return resolve()


class FakeDownloadExpectation:
    async def __aenter__(self) -> FakeDownloadInfo:
        return FakeDownloadInfo()

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        return None


class NavigationDownloadPage:
    def expect_download(self, timeout: int) -> FakeDownloadExpectation:
        assert timeout == 12_000
        return FakeDownloadExpectation()

    async def goto(self, _url: str, wait_until: str, timeout: int) -> None:
        assert wait_until == "commit"
        assert timeout == 12_000
        raise RuntimeError("Download is starting")

    async def close(self) -> None:
        return None


class NavigationContext(FakeContext):
    async def new_page(self) -> NavigationDownloadPage:
        return NavigationDownloadPage()


class NavigationPage:
    def __init__(self) -> None:
        self.context = NavigationContext(FakeRequest(FakeResponse(b"unused")))


@pytest.mark.asyncio
async def test_attachment_checkpoint_reuses_nonempty_local_file(tmp_path: Path) -> None:
    channel_id = "ui-channel:one"
    url = "https://example.test/file.pdf"
    attachment_id = stable_hash("1000", url)
    target_dir = tmp_path / "files" / storage_key(channel_id) / attachment_id
    target_dir.mkdir(parents=True)
    existing = target_dir / "file.pdf"
    existing.write_bytes(b"pdf")
    messages = [{"id": "1000", "attachments": [{"name": "file.pdf", "url": url}]}]
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

    await extractor._download_attachments(MissingAttachmentCardPage(), channel_id, messages)

    attachment = messages[0]["attachments"][0]
    assert attachment["status"] == "local"
    assert attachment["localPath"] == str(existing)
    assert attachment["sizeBytes"] == 3


@pytest.mark.asyncio
async def test_attachment_outside_rendered_batch_stays_pending(tmp_path: Path) -> None:
    messages = [{
        "id": "1000",
        "attachments": [{"name": "file.pdf", "url": "https://example.test/file.pdf"}],
    }]
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

    await extractor._download_attachments(MissingAttachmentCardPage(), "ui-channel:one", messages)

    attachment = messages[0]["attachments"][0]
    assert attachment["status"] == "pending"
    assert attachment.get("errorCode") is None


@pytest.mark.asyncio
async def test_rendered_sharepoint_url_fallback_saves_nonempty_file(tmp_path: Path) -> None:
    url = "https://tenant.sharepoint.com/sites/client/file.pdf"
    messages = [{"id": "1000", "attachments": [{"name": "file.pdf", "url": url}]}]
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

    await extractor._download_attachment_fallbacks(
        DirectDownloadPage(FakeResponse(b"pdf-content")), "ui-channel:one", messages, {},
    )

    attachment = messages[0]["attachments"][0]
    assert attachment["status"] == "local"
    assert attachment["captureMode"] == "rendered-url"
    assert Path(attachment["localPath"]).read_bytes() == b"pdf-content"


@pytest.mark.asyncio
async def test_rendered_url_fallback_rejects_html_login_page(tmp_path: Path) -> None:
    url = "https://tenant.sharepoint.com/sites/client/file.pdf"
    messages = [{"id": "1000", "attachments": [{"name": "file.pdf", "url": url}]}]
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

    await extractor._download_attachment_fallbacks(
        DirectDownloadPage(FakeResponse(b"<html>login</html>", "text/html")),
        "ui-channel:one", messages, {},
    )

    attachment = messages[0]["attachments"][0]
    assert attachment["status"] == "failed"
    assert attachment["errorCode"] == "source-returned-html"
    assert not list((tmp_path / "files").rglob("*.pdf"))


@pytest.mark.asyncio
async def test_rendered_url_fallback_forces_sharepoint_download_mode(tmp_path: Path) -> None:
    url = "https://tenant.sharepoint.com/sites/client/file.pdf?web=1"
    messages = [{"id": "1000", "attachments": [{"name": "file.pdf", "url": url}]}]
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

    await extractor._download_attachment_fallbacks(
        DownloadQueryPage(), "ui-channel:one", messages, {},
    )

    attachment = messages[0]["attachments"][0]
    assert attachment["status"] == "local"
    assert Path(attachment["localPath"]).read_bytes() == b"forced-download"


@pytest.mark.asyncio
async def test_browser_navigation_fallback_captures_download_event(tmp_path: Path) -> None:
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

    result = await extractor._download_via_browser_navigation(
        NavigationPage(), "https://tenant.sharepoint.com/sites/client/file.pdf",
        tmp_path / "files", "fallback.pdf",
    )

    assert result is not None
    assert result["status"] == "local"
    assert result["captureMode"] == "browser-navigation"
    assert Path(result["localPath"]).read_bytes() == b"browser-download"
