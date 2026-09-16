import asyncio

import pytest
from playwright.async_api import async_playwright

from teams_archive.capture.browser import chrome_executable
from teams_archive.capture.extractor import TeamsDomExtractor, trusted_teams_url


def test_only_saved_https_teams_urls_are_navigable() -> None:
    assert trusted_teams_url("https://teams.cloud.microsoft/v2/?channel=stored")
    assert trusted_teams_url("https://teams.microsoft.com/l/channel/stored")
    assert not trusted_teams_url("https://example.com/not-teams")
    assert not trusted_teams_url("https://user:password@teams.cloud.microsoft/v2/")
    assert not trusted_teams_url("https://teams.cloud.microsoft:1234/v2/")
    assert not trusted_teams_url("https://teams.cloud.microsoft:bad/v2/")


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


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_channel_viewport_falls_back_to_scrollable_message_parent(tmp_path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.set_content("""
          <main id="message-pane-layout-a11y">
            <div id="current-channel-scroll" style="height:100px; overflow-y:auto">
              <div style="height:1000px">
                <div data-tid="channel-pane-message" id="reply-chain-summary-1000">Post</div>
              </div>
            </div>
          </main>
        """)
        extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")
        viewport = await extractor._channel_viewport(page)
        viewport_id = await viewport.get_attribute("id")
        await browser.close()

    assert viewport_id == "current-channel-scroll"


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_channel_navigation_uses_saved_url_after_chrome_reopens(tmp_path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.set_content("""
          <title>Teams and Channels | Client | Legal | Microsoft Teams</title>
          <div data-tid="channelTitle-text">Legal</div>
          <div data-tid="response-surface" id="response-surface-wrong-source"></div>
        """)
        saved_url = "https://teams.cloud.microsoft/v2/?channel=stored"
        await page.route(saved_url, lambda route: route.fulfill(body="""
          <title>Teams and Channels | Client | Legal | Microsoft Teams</title>
          <div data-tid="experience-layout">
            <div data-tid="channelTitle-text">Legal</div>
            <div data-tid="response-surface" id="response-surface-right-source"></div>
          </div>
        """, content_type="text/html"))
        extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

        await extractor.navigate_to_channel(
            page, "Client", "Legal", saved_url, "right-source",
        )

        assert page.url == saved_url
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_channel_navigation_waits_for_teams_after_reopen_without_saved_url(tmp_path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.set_content("<main>Loading Teams</main>")

        async def render_teams() -> None:
            await asyncio.sleep(0.2)
            await page.set_content("""
              <title>Teams and Channels | Client | Legal | Microsoft Teams</title>
              <div data-tid="experience-layout">
                <div role="treeitem" aria-label="Client Legal" onclick="
                  document.getElementById('channel').textContent='Legal'
                ">Legal</div>
                <div data-tid="channelTitle-text" id="channel">Home</div>
              </div>
            """)

        rendering = asyncio.create_task(render_teams())
        extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")
        await extractor.navigate_to_channel(page, "Client", "Legal")
        await rendering

        assert await page.locator('[data-tid="channelTitle-text"]').text_content() == "Legal"
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not chrome_executable(), reason="Google Chrome Stable is required")
async def test_channel_navigation_ignores_untrusted_saved_url(tmp_path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.set_content("""
          <title>Teams and Channels | Client | Home | Microsoft Teams</title>
          <div data-tid="experience-layout">
            <div role="treeitem" aria-label="Client Legal" onclick="
              document.getElementById('channel').textContent='Legal';
              document.title='Teams and Channels | Client | Legal | Microsoft Teams'
            ">Legal</div>
            <div data-tid="channelTitle-text" id="channel">Home</div>
          </div>
        """)
        extractor = TeamsDomExtractor(tmp_path / "files", tmp_path / "assets")

        await extractor.navigate_to_channel(
            page, "Client", "Legal", "https://example.com/not-teams",
        )

        assert page.url == "about:blank"
        await browser.close()
