import asyncio
import time
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

import teams_archive.capture.extractor as extractor_module
from teams_archive.capture.browser import chrome_executable
from teams_archive.capture.extractor import (
    FORBIDDEN_ACTION_NAMES,
    TeamsDomExtractor,
    message_capture_key,
    safe_filename,
    stable_hash,
    storage_key,
    team_from_title,
    trusted_sharepoint_url,
)
from teams_archive.capture.service import sanitize_post


def test_capture_helpers_are_stable_and_cross_platform_safe() -> None:
    assert stable_hash("A", "B") == stable_hash("A", "B")
    assert storage_key("ui-channel:abc") == storage_key("ui-channel:abc")
    assert len(storage_key("ui-channel:abc")) == 32
    assert all(character in "0123456789abcdef" for character in storage_key("ui-channel:abc"))
    assert safe_filename('a<b>:c?.pdf') == "a_b__c_.pdf"
    assert team_from_title("Teams and Channels | Client | Legal | Microsoft Teams", "Legal") == "Client"
    assert trusted_sharepoint_url("https://tenant.sharepoint.com/sites/client/file.pdf")
    assert not trusted_sharepoint_url("https://tenant.sharepoint.com.evil.test/file.pdf")
    assert not trusted_sharepoint_url("https://user:password@tenant.sharepoint.com/file.pdf")


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
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets", avoid_browser_downloads=False)

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
    extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets", avoid_browser_downloads=False)

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


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_browser_stream_captures_preview_file_without_download_item(tmp_path: Path) -> None:
    payload = b"streamed-file-content" * 8192
    url = "https://tenant.sharepoint.com/preview"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(accept_downloads=True)
        download_events = []
        context.on("page", lambda opened: opened.on(
            "download", lambda event: download_events.append(event)
        ))

        async def route_file(route):
            if route.request.url == url:
                await route.fulfill(
                    body="<html><iframe src='/file'></iframe></html>",
                    content_type="text/html",
                )
            else:
                await route.fulfill(
                    body=payload,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Disposition": 'attachment; filename="report.bin"',
                    },
                )

        await context.route("https://tenant.sharepoint.com/**", route_file)
        page = await context.new_page()
        extractor = TeamsDomExtractor(
            tmp_path / "files", tmp_path / "assets", avoid_browser_downloads=True,
        )
        messages = [{"id": "1000", "attachments": [{"name": "fallback.bin", "url": url}]}]

        await extractor._download_attachments(page, "ui-channel:one", messages)

        attachment = messages[0]["attachments"][0]
        assert attachment["status"] == "local"
        assert attachment["captureMode"] == "browser-stream"
        assert Path(attachment["localPath"]).read_bytes() == payload
        assert download_events == []
        await browser.close()


@pytest.mark.asyncio
async def test_safe_download_fallback_never_uses_browser_download_item(tmp_path: Path) -> None:
    url = "https://tenant.sharepoint.com/sites/client/file.pdf"
    messages = [{"id": "1000", "attachments": [{"name": "file.pdf", "url": url}]}]
    extractor = TeamsDomExtractor(
        tmp_path / "files", tmp_path / "assets", avoid_browser_downloads=True,
    )

    async def unexpected_browser_download(*_args):
        raise AssertionError("browser download item must not be created")

    extractor._download_via_browser_navigation = unexpected_browser_download
    await extractor._download_attachment_fallbacks(
        DirectDownloadPage(FakeResponse(b"pdf-content")), "ui-channel:one", messages, {},
    )

    attachment = messages[0]["attachments"][0]
    assert attachment["status"] == "local"
    assert Path(attachment["localPath"]).read_bytes() == b"pdf-content"


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_stalled_browser_stream_times_out_and_closes_temporary_tab(tmp_path: Path, monkeypatch) -> None:
    release_response = asyncio.Event()
    response_started = asyncio.Event()

    async def serve_stalled_file(reader, writer) -> None:
        await reader.read(4096)
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/octet-stream\r\n"
            b"Content-Length: 1000000\r\n"
            b"Content-Disposition: attachment; filename=stalled.bin\r\n\r\npartial"
        )
        await writer.drain()
        response_started.set()
        await release_response.wait()
        writer.close()

    server = await asyncio.start_server(serve_stalled_file, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"http://127.0.0.1:{port}/stalled"
    monkeypatch.setattr(extractor_module, "trusted_sharepoint_url", lambda value: value == url)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            extractor = TeamsDomExtractor(
                tmp_path / "files", tmp_path / "assets", avoid_browser_downloads=True,
            )
            started = time.monotonic()
            task = asyncio.create_task(extractor._download_via_browser_stream(
                page, url, tmp_path / "files" / "target", "stalled.bin", timeout_seconds=2.0,
            ))
            done, pending = await asyncio.wait({task}, timeout=6.0)
            release_response.set()
            if pending:
                task.cancel()
            assert done, "a stalled file must not hold the capture task"
            assert task.result() is None
            assert response_started.is_set()
            assert time.monotonic() - started < 6.0
            assert len(context.pages) == 1
            assert not list((tmp_path / "files" / "target").glob("*"))
            await browser.close()
    finally:
        release_response.set()
        server.close()
        await server.wait_closed()
