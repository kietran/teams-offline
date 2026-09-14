import pytest
from playwright.async_api import async_playwright

from teams_archive.capture.browser import chrome_executable
from teams_archive.capture.extractor import TeamsDomExtractor


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_dom_identity_and_messages_use_proven_teams_selectors(tmp_path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.set_content("""
          <div data-tid="channelTitle-text">Legal</div>
          <div data-tid="response-surface" id="response-surface-19:abc@thread.tacv2" aria-label="1 reply"></div>
          <div data-tid="channel-replies-pane-message">
            <span data-tid="post-message-header-avatar" aria-label="Profile picture of Lan."></span>
            <time data-tid="timestamp" aria-label="September 14, 2026"></time>
            <h2 data-tid="subject-line">Update</h2>
            <div data-tid="message-body" id="content-1789315200000"><p>Hello</p></div>
            <div data-tid="file-attachment-grid"><div role="group" aria-label="report.pdf https://sharepoint.test/report.pdf"></div></div>
          </div>
          <div data-tid="channel-replies-pane-message">
            <span data-tid="reply-message-header-avatar" aria-label="Profile picture of Nam."></span>
            <div data-tid="message-body" id="content-1789315260000"><p>Reply</p></div>
          </div>
        """)
        await page.evaluate("document.title='Teams and Channels | Client | Legal | Microsoft Teams'")
        extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")
        identity = await extractor.discover_current_channel(page)
        messages = await extractor._extract_messages(page, '[data-tid="channel-replies-pane-message"]')
        await browser.close()

    assert identity.team_name == "Client"
    assert identity.source_locator == "19:abc@thread.tacv2"
    assert identity.identity_confidence == "source_id"
    assert [message["id"] for message in messages] == ["1789315200000", "1789315260000"]
    assert messages[0]["attachments"][0]["name"] == "report.pdf"
    assert messages[1]["author"] == "Nam"


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_inline_replies_are_split_from_one_channel_root(tmp_path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.set_content("""
          <div data-tid="channel-pane-message" id="reply-chain-summary-1000" role="group">
            <span data-tid="post-message-header-avatar" aria-label="Profile picture of Lan."></span>
            <h2 data-tid="subject-line">Root</h2><div data-tid="message-body" id="content-1000000000000">Root body</div>
            <div role="group"><span data-tid="reply-message-header-avatar" aria-label="Profile picture of Nam."></span><div data-tid="message-body" id="content-1000000000001">Reply one</div></div>
            <div role="group"><span data-tid="reply-message-header-avatar" aria-label="Profile picture of Hoa."></span><div data-tid="message-body" id="content-1000000000002">Reply two</div></div>
          </div>
        """)
        extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")
        messages = await extractor._extract_inline_messages(page, "1000")
        await browser.close()
    assert [message["text"] for message in messages] == ["Root body", "Reply one", "Reply two"]
    assert [message["author"] for message in messages] == ["Lan", "Nam", "Hoa"]
