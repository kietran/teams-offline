from __future__ import annotations

import asyncio
import base64
import hashlib
import mimetypes
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from .models import ChannelIdentity


FORBIDDEN_ACTION_NAMES = {"send", "share", "edit", "delete", "reply in thread"}
CHANNEL_SURFACE_SELECTOR = (
    '[data-tid="channel-pane-viewport"], #message-pane-layout-a11y, '
    '[data-tid="channel-pane-message"], [id^="reply-chain-summary-"]'
)
CHANNEL_MESSAGE_SELECTOR = '[data-tid="channel-pane-message"], [id^="reply-chain-summary-"]'
TEAMS_HOSTS = {"teams.cloud.microsoft", "teams.microsoft.com"}


def trusted_teams_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https" and parsed.hostname in TEAMS_HOSTS
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def trusted_sharepoint_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.hostname.endswith(".sharepoint.com")
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def storage_key(identifier: str) -> str:
    """Return a deterministic directory name safe on every supported platform."""
    return stable_hash(identifier)[:32]


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(" .")
    return cleaned[:180] or "attachment"


def message_capture_key(message: dict[str, Any]) -> str:
    """Deduplicate messages harvested from overlapping virtualized batches."""
    message_id = message.get("id")
    if message_id:
        return f"id:{message_id}"
    if message.get("captureKey"):
        return f"source:{message['captureKey']}"
    return "fallback:" + stable_hash(
        message.get("author") or "",
        message.get("timestamp") or message.get("timestampLabel") or "",
        message.get("text") or "",
    )


def team_from_title(page_title: str, channel_name: str) -> str:
    parts = [part.strip() for part in page_title.split("|")]
    if len(parts) >= 4 and parts[0].startswith("Teams"):
        return parts[-3]
    return "Teams"


class TeamsDomExtractor:
    def __init__(
        self, files_root: Path, assets_root: Path,
        avoid_browser_downloads: bool | None = None,
    ) -> None:
        self.files_root = files_root
        self.assets_root = assets_root
        self.avoid_browser_downloads = (
            sys.platform == "win32" if avoid_browser_downloads is None else avoid_browser_downloads
        )

    async def _channel_viewport(self, page: Any) -> Any:
        """Find the channel scroller without depending on one Teams DOM version."""
        surface = page.locator(CHANNEL_SURFACE_SELECTOR).first
        await surface.wait_for(state="visible", timeout=30_000)

        legacy = page.locator('[data-tid="channel-pane-viewport"]').first
        if await legacy.count() and await legacy.is_visible():
            return legacy

        message = page.locator(CHANNEL_MESSAGE_SELECTOR).first
        for _ in range(20):
            if await message.count() and await message.is_visible():
                handle = await message.evaluate_handle("""element => {
                  for (let node = element.parentElement; node; node = node.parentElement) {
                    const style = getComputedStyle(node);
                    if (/(auto|scroll|overlay)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) {
                      return node;
                    }
                  }
                  return element.closest('#message-pane-layout-a11y, [role="feed"], [role="main"]')
                    || document.scrollingElement;
                }""")
                element = handle.as_element()
                if element:
                    return element
            await asyncio.sleep(0.25)
        return surface

    async def navigate_to_channel(
        self, page: Any, team_name: str, channel_name: str,
        web_url: str | None = None, source_locator: str | None = None,
    ) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        async def at_target() -> bool:
            title_node = page.locator('[data-tid="channelTitle-text"]').first
            if not await title_node.count():
                return False
            current = (await title_node.text_content(timeout=1_000) or "").strip()
            if current != channel_name:
                return False
            if source_locator:
                observed = await page.evaluate(r"""() => {
                  const id = document.querySelector('[data-tid="response-surface"][id^="response-surface-"]')?.id;
                  return id ? id.slice('response-surface-'.length) : null;
                }""")
                if observed and observed != source_locator:
                    return False
            visible_team = team_from_title(await page.title(), current)
            return visible_team == "Teams" or visible_team == team_name

        if await at_target():
            return

        # A reopened Chrome profile starts on Teams home, and its channel tree
        # may not exist yet. A saved Teams URL is the most reliable route back.
        if web_url and trusted_teams_url(web_url):
            try:
                await page.goto(web_url, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                pass
            try:
                await page.locator('[data-tid="channelTitle-text"]').first.wait_for(
                    state="visible", timeout=30_000,
                )
            except PlaywrightTimeoutError:
                pass
            if await at_target():
                return

        try:
            await page.locator('[data-tid="experience-layout"]').first.wait_for(
                state="visible", timeout=45_000,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("channel-not-visible") from exc

        tree_items = page.get_by_role("treeitem").filter(has_text=channel_name)
        for index in range(await tree_items.count()):
            item = tree_items.nth(index)
            label = await item.get_attribute("aria-label") or ""
            if team_name in label or await tree_items.count() == 1:
                await item.click(timeout=10_000)
                await page.locator('[data-tid="channelTitle-text"]').filter(has_text=channel_name).wait_for(timeout=15_000)
                if await at_target():
                    return
        await page.keyboard.press("Control+Alt+G")
        combobox = page.get_by_role("combobox", name=re.compile("chat or channel", re.IGNORECASE))
        try:
            await combobox.wait_for(state="visible", timeout=3_000)
            await combobox.fill(channel_name)
            await asyncio.sleep(1.2)
            candidates = page.get_by_role("option").filter(has_text=channel_name)
            for index in range(await candidates.count()):
                candidate = candidates.nth(index)
                label = await candidate.get_attribute("aria-label") or await candidate.text_content() or ""
                if await candidate.is_visible() and (team_name in label or await candidates.count() == 1):
                    await candidate.click(timeout=8_000)
                    await page.locator('[data-tid="channelTitle-text"]').filter(has_text=channel_name).wait_for(timeout=15_000)
                    if await at_target():
                        return
        except Exception:
            pass
        await page.keyboard.press("Escape")
        raise RuntimeError("channel-not-visible")

    async def discover_current_channel(self, page: Any) -> ChannelIdentity:
        title_node = page.locator('[data-tid="channelTitle-text"]')
        if await title_node.count() == 0:
            raise RuntimeError("not-on-channel")
        display_name = (await title_node.text_content() or "").strip()
        if not display_name:
            raise RuntimeError("not-on-channel")
        page_title = await page.title()
        team_name = team_from_title(page_title, display_name)
        source_locator = await page.evaluate(r"""() => {
          const value = document.querySelector('[data-tid="response-surface"][id^="response-surface-"]')?.id;
          return value ? value.slice('response-surface-'.length) : null;
        }""")
        confidence = "source_id" if source_locator else "name_fingerprint"
        locator = source_locator or stable_hash(team_name.casefold(), display_name.casefold())
        team_id = "ui-team:" + stable_hash(team_name.casefold())[:24]
        channel_id = "ui-channel:" + stable_hash(locator)[:32]
        membership = "shared" if "Shared Channel" in page_title else "unknown"
        return ChannelIdentity(
            id=channel_id, team_id=team_id, team_name=team_name,
            display_name=display_name, source_locator=locator,
            identity_confidence=confidence, membership_type=membership,
            web_url=page.url,
        )

    async def _root_summaries(self, page: Any) -> list[dict[str, Any]]:
        return await page.evaluate(r"""() => [...document.querySelectorAll('[data-tid="channel-pane-message"]')].map(el => {
          const root = el.id.match(/reply-chain-summary-(\d{10,})/);
          const replies = el.querySelector('[data-tid="response-surface"]')?.getAttribute('aria-label')?.match(/(\d+)\s+repl/i);
          return {id: root?.[1] || null, expectedReplies: replies ? Number(replies[1]) : 0,
            hasReplyButton: Boolean(el.querySelector('[data-tid="response-summary-button"]'))};
        })""")

    async def _extract_messages(self, page: Any, selector: str) -> list[dict[str, Any]]:
        return await page.evaluate(r"""selector => {
          const elements = [...document.querySelectorAll(selector)];
          const messageId = el => el.querySelector('[data-tid="message-body"]')?.id?.match(/content-(\d{10,})/)?.[1] || null;
          const ids = elements.map(messageId);
          return elements.map((el, index) => {
          const clean = value => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
          const body = el.querySelector('[data-tid="message-body"]');
          const id = ids[index];
          const avatar = el.querySelector('[data-tid="post-message-header-avatar"][aria-label], [data-tid="reply-message-header-avatar"][aria-label]');
          const explicit = el.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label') || null;
          let captureKey = null;
          if (!id) {
            let previous = index - 1;
            while (previous >= 0 && !ids[previous]) previous -= 1;
            if (previous >= 0) {
              captureKey = `after:${ids[previous]}:${index - previous}`;
            } else {
              let next = index + 1;
              while (next < ids.length && !ids[next]) next += 1;
              captureKey = `before:${next < ids.length ? ids[next] : 'end'}:${next - index}`;
            }
          }
          const attachments = []; const seen = new Set();
          for (const grid of el.querySelectorAll('[data-tid="file-attachment-grid"]')) {
            const nodes = [grid, ...grid.querySelectorAll('[aria-label*="http"]')];
            const label = nodes.map(node => node.getAttribute('aria-label') || '').find(value => /https?:\/\//.test(value)) || '';
            const match = label.match(/https?:\/\/\S+/);
            if (!match) continue; const url = match[0]; const name = clean(label.slice(0, match.index));
            if (!seen.has(url)) { seen.add(url); attachments.push({name, url}); }
          }
          return {id, order:index, author:(avatar?.getAttribute('aria-label') || '').replace(/^Profile picture of /,'').replace(/\.$/, '') || null,
            timestamp:id && /^\d{13}$/.test(id) ? new Date(Number(id)).toISOString() : explicit,
            timestampLabel:explicit, subject:clean(el.querySelector('[data-tid="subject-line"]')?.textContent),
            text:el.querySelector('[data-tid="message-tombstone"]') ? '[This message has been deleted.]' : clean(body?.innerText),
            html:el.querySelector('[data-tid="message-tombstone"]') ? '' : (body?.innerHTML || ''),
            deleted:Boolean(el.querySelector('[data-tid="message-tombstone"]')), captureKey, attachments,
            images:[...body?.querySelectorAll('img') || []].map(img => ({alt:img.alt || '', src:img.src || ''}))};
          });
        }""", selector)

    async def _extract_inline_messages(self, page: Any, post_id: str) -> list[dict[str, Any]]:
        return await page.evaluate(r"""postId => {
          const clean = value => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
          const root = document.querySelector(`#reply-chain-summary-${postId}`);
          if (!root) return [];
          return [...root.querySelectorAll('[data-tid="message-body"]')].map((body, index) => {
            const el = body.closest('[role="group"]') || body.parentElement;
            const id = body.id?.match(/content-(\d{10,})/)?.[1] || null;
            const avatar = el.querySelector('[data-tid="post-message-header-avatar"][aria-label], [data-tid="reply-message-header-avatar"][aria-label]');
            const explicit = el.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label') || null;
            const attachments=[]; const seen=new Set();
            for (const grid of el.querySelectorAll('[data-tid="file-attachment-grid"]')) {
              const nodes=[grid,...grid.querySelectorAll('[aria-label*="http"]')];
              const label=nodes.map(node=>node.getAttribute('aria-label')||'').find(value=>/https?:\/\//.test(value))||'';
              const match=label.match(/https?:\/\/\S+/);
              if(match&&!seen.has(match[0])){seen.add(match[0]);attachments.push({name:clean(label.slice(0,match.index)),url:match[0]});}
            }
            return {id,order:index,author:(avatar?.getAttribute('aria-label')||'').replace(/^Profile picture of /,'').replace(/\.$/,'')||null,
              timestamp:id&&/^\d{13}$/.test(id)?new Date(Number(id)).toISOString():explicit,timestampLabel:explicit,
              subject:index===0?clean(root.querySelector('[data-tid="subject-line"]')?.textContent):'',text:clean(body.innerText),html:body.innerHTML||'',deleted:false,attachments,
              images:[...body.querySelectorAll('img')].map(img=>({alt:img.alt||'',src:img.src||''}))};
          });
        }""", post_id)

    async def _load_thread(
        self,
        page: Any,
        channel_id: str,
        post_id: str,
        root_message: dict[str, Any],
        expected_replies: int,
        download_results: dict[str, dict[str, Any]],
        asset_results: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        viewport = page.locator('[data-tid="channel-replies-viewport"]')
        await viewport.wait_for(state="visible", timeout=15_000)
        captured: dict[str, tuple[int, dict[str, Any]]] = {}
        discovery_order = 0
        previous = -1
        stable = 0

        async def harvest() -> None:
            nonlocal discovery_order
            batch = await self._extract_messages(page, '[data-tid="channel-replies-pane-message"]')
            await self._save_assets(page, channel_id, batch, asset_results)
            await self._download_attachments(page, channel_id, batch, download_results)
            for message in batch:
                if message.get("id") == post_id:
                    continue
                key = message_capture_key(message)
                if key not in captured:
                    captured[key] = (discovery_order, message)
                    discovery_order += 1
                else:
                    first_seen, _ = captured[key]
                    captured[key] = (first_seen, message)

        await harvest()
        for _ in range(80):
            if len(captured) >= expected_replies:
                break
            await viewport.evaluate("el => { el.scrollTop=0; el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
            await asyncio.sleep(0.65)
            await harvest()
            count = len(captured)
            stable = stable + 1 if count == previous else 0
            previous = count
            if stable >= 3 and expected_replies <= 0:
                break

        def unresolved_urls() -> set[str]:
            urls = {
                item.get("url")
                for _, message in captured.values()
                for item in message.get("attachments", [])
                if item.get("url")
            }
            return {
                url for url in urls
                if not download_results.get(url)
                or (
                    download_results[url].get("status") != "local"
                    and download_results[url].get("attempts", 0) < 2
                )
            }

        # Once Teams has loaded the whole virtualized thread, sweep its scroll
        # range so attachment cards that were detached during the upward load
        # get another chance to render and download.
        for _pass in range(2):
            if not unresolved_urls():
                break
            await viewport.evaluate(
                "el => { el.scrollTop=0; el.dispatchEvent(new Event('scroll',{bubbles:true})); }"
            )
            await asyncio.sleep(0.4)
            for _ in range(80):
                batch = await self._extract_messages(page, '[data-tid="channel-replies-pane-message"]')
                await self._save_assets(page, channel_id, batch, asset_results)
                await self._download_attachments(page, channel_id, batch, download_results)
                metrics = await viewport.evaluate(
                    "el => ({top:el.scrollTop, height:el.scrollHeight, client:el.clientHeight})"
                )
                bottom = max(0, metrics["height"] - metrics["client"])
                if metrics["top"] >= bottom - 1:
                    break
                next_top = min(bottom, metrics["top"] + max(500, metrics["client"] * 0.75))
                await viewport.evaluate(
                    "(el, top) => { el.scrollTop=top; el.dispatchEvent(new Event('scroll',{bubbles:true})); }",
                    next_top,
                )
                await asyncio.sleep(0.4)

        all_messages = [root_message, *[message for _, message in captured.values()]]
        await self._download_attachment_fallbacks(
            page, channel_id, all_messages, download_results,
        )
        for _, message in captured.values():
            for item in message.get("attachments", []):
                result = download_results.get(item.get("url") or "")
                if result:
                    item.update({key: value for key, value in result.items() if key != "attempts"})

        def reply_order(item: tuple[int, dict[str, Any]]) -> tuple[int, int | str, int]:
            first_seen, message = item
            message_id = message.get("id") or ""
            if message_id.isdigit():
                return (0, int(message_id), first_seen)
            timestamp = message.get("timestamp") or message.get("timestampLabel") or ""
            return (1, timestamp, first_seen)

        replies = [message for _, message in sorted(captured.values(), key=reply_order)]
        return [{**root_message, "id": post_id, "order": 0}, *replies], stable

    async def _save_assets(
        self,
        page: Any,
        channel_id: str,
        messages: list[dict[str, Any]],
        results: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        results = results if results is not None else {}
        for message in messages:
            message_id = message.get("id") or message_capture_key(message)
            saved = []
            for index, image in enumerate(message.get("images", [])):
                src = image.get("src") or ""
                asset_id = stable_hash(message_id, src or str(index))
                if asset_id in results:
                    saved.append({**image, **results[asset_id]})
                    continue
                target_dir = self.assets_root / storage_key(channel_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                stored = None
                capture_mode = "original"
                mime_type = None
                existing = next(
                    (path for path in target_dir.glob(f"{asset_id}.*") if path.is_file() and path.stat().st_size > 0),
                    None,
                )
                if existing:
                    stored = existing
                    mime_type = mimetypes.guess_type(existing.name)[0]
                if stored is None and src.startswith("http"):
                    try:
                        response = await page.context.request.get(src, timeout=15_000)
                        mime_type = (response.headers.get("content-type") or "image/png").split(";", 1)[0]
                        if response.ok and mime_type.startswith("image/"):
                            extension = mimetypes.guess_extension(mime_type) or ".img"
                            stored = target_dir / f"{asset_id}{extension}"
                            stored.write_bytes(await response.body())
                    except Exception:
                        stored = None
                if stored is None:
                    locator = page.locator(f'[data-tid="message-body"]#{"content-" + message_id} img').nth(index)
                    if await locator.count():
                        stored = target_dir / f"{asset_id}.png"
                        await locator.screenshot(path=str(stored))
                        mime_type = "image/png"
                        capture_mode = "screenshot"
                if stored:
                    result = {
                        "id": asset_id, "localPath": str(stored), "sizeBytes": stored.stat().st_size,
                        "mimeType": mime_type, "captureMode": capture_mode,
                    }
                    results[asset_id] = result
                    saved.append({**image, **result})
            message["images"] = saved

    async def _download_attachments(
        self,
        page: Any,
        channel_id: str,
        messages: list[dict[str, Any]],
        results: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        results = results if results is not None else {}
        for message in messages:
            message_id = message.get("id") or message_capture_key(message)
            for index, item in enumerate(message.get("attachments", [])):
                url = item.get("url") or ""
                attachment_id = stable_hash(message_id, url or f"{item.get('name', '')}:{index}")
                item.update({"id": attachment_id, "captureMode": "download"})
                cached = results.get(url) if url else None
                if cached and (cached.get("status") == "local" or cached.get("attempts", 0) >= 2):
                    item.update({key: value for key, value in cached.items() if key != "attempts"})
                    item["id"] = attachment_id
                    continue
                target_dir = self.files_root / storage_key(channel_id) / attachment_id
                target_dir.mkdir(parents=True, exist_ok=True)
                existing = next(
                    (path for path in target_dir.iterdir() if path.is_file() and path.stat().st_size > 0),
                    None,
                )
                if existing:
                    result = {
                        "localPath": str(existing), "status": "local", "errorCode": None,
                        "sizeBytes": existing.stat().st_size,
                        "mimeType": mimetypes.guess_type(existing.name)[0],
                    }
                    results[url] = result
                    item.update(result)
                    continue
                if not url:
                    item.update({"localPath": None, "status": "failed", "errorCode": "missing-source-url"})
                    continue

                if self.avoid_browser_downloads:
                    result = await self._download_via_browser_stream(
                        page, url, target_dir, item.get("name") or "attachment",
                    )
                    if result:
                        results[url] = result
                        item.update(result)
                    else:
                        attempts = int(cached.get("attempts", 0)) if cached else 0
                        result = {
                            "localPath": None, "status": "failed",
                            "errorCode": "browser-stream-unavailable", "attempts": attempts + 1,
                        }
                        results[url] = result
                        item.update({key: value for key, value in result.items() if key != "attempts"})
                    continue

                marker = f"archive-{attachment_id[:24]}"
                found = await page.evaluate(r"""({url, marker}) => {
                  for (const grid of document.querySelectorAll('[data-tid="file-attachment-grid"]')) {
                    const nodes = [grid, ...grid.querySelectorAll('[aria-label]')];
                    const matches = nodes.some(node => {
                      const value = node.getAttribute('aria-label') || '';
                      return value.match(/https?:\/\/\S+/)?.[0] === url;
                    });
                    if (matches) {
                      grid.setAttribute('data-archive-download-key', marker);
                      return true;
                    }
                  }
                  return false;
                }""", {"url": url, "marker": marker})
                if not found:
                    item.setdefault("status", "pending")
                    continue

                attempts = int(cached.get("attempts", 0)) if cached else 0
                phase = "download-button"
                try:
                    card = page.locator(f'[data-archive-download-key="{marker}"]').first
                    more_actions = card.get_by_role("button", name="More actions")
                    if await more_actions.count() == 0:
                        more_actions = card.locator('button[aria-label=""]').last
                    await more_actions.click(timeout=3_000)
                    phase = "download-action"
                    async with page.expect_download(timeout=8_000) as pending:
                        await page.get_by_role(
                            "menuitem", name=re.compile(r"^(Download|Tải xuống)$", re.IGNORECASE)
                        ).click(timeout=2_000)
                    phase = "download-event"
                    download = await pending.value
                    target = target_dir / safe_filename(download.suggested_filename or item.get("name") or "attachment")
                    phase = "download-save"
                    await download.save_as(str(target))
                    result = {
                        "localPath": str(target), "status": "local", "errorCode": None,
                        "sizeBytes": target.stat().st_size,
                        "mimeType": mimetypes.guess_type(target.name)[0],
                    }
                    results[url] = result
                    item.update(result)
                except Exception as exc:
                    result = {
                        "localPath": None, "status": "failed",
                        "errorCode": f"{phase}-{type(exc).__name__}",
                        "attempts": attempts + 1,
                    }
                    results[url] = result
                    item.update({key: value for key, value in result.items() if key != "attempts"})
                    try:
                        await page.keyboard.press("Escape")
                    except Exception:
                        pass

    async def _download_via_browser_stream(
        self, page: Any, url: str, target_dir: Path, fallback_name: str,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any] | None:
        """Stream a rendered SharePoint file through Chrome without a download item."""
        if not trusted_sharepoint_url(url):
            return None

        target_dir.mkdir(parents=True, exist_ok=True)
        download_page = await page.context.new_page()
        session = await page.context.new_cdp_session(download_page)
        loop = asyncio.get_running_loop()
        finished: asyncio.Future[dict[str, Any]] = loop.create_future()
        handlers: set[asyncio.Task[None]] = set()
        navigation: asyncio.Task[Any] | None = None

        async def handle_response(event: dict[str, Any]) -> None:
            request_id = event["requestId"]
            headers = {
                header["name"].lower(): header["value"]
                for header in event.get("responseHeaders", [])
            }
            mime_type = headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
            status = int(event.get("responseStatusCode") or 0)
            response_url = event.get("request", {}).get("url", "")
            if (
                status != 200 or not trusted_sharepoint_url(response_url)
                or mime_type in {"text/html", "application/xhtml+xml"}
            ):
                try:
                    await session.send("Fetch.continueRequest", {"requestId": request_id})
                except Exception as exc:
                    if not finished.done():
                        finished.set_exception(exc)
                return

            temporary: Path | None = None
            stream_handle: str | None = None
            try:
                stream_handle = (await session.send(
                    "Fetch.takeResponseBodyAsStream", {"requestId": request_id}
                ))["stream"]
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=".archive-download-", dir=self.files_root, delete=False,
                ) as output:
                    temporary = Path(output.name)
                    while True:
                        chunk = await session.send("IO.read", {"handle": stream_handle, "size": 65536})
                        body = (
                            base64.b64decode(chunk["data"])
                            if chunk.get("base64Encoded") else chunk["data"].encode()
                        )
                        output.write(body)
                        if chunk["eof"]:
                            break
                if temporary.stat().st_size == 0:
                    raise RuntimeError("source-empty")
                with temporary.open("rb") as check:
                    if check.read(256).lstrip().lower().startswith((b"<!doctype html", b"<html")):
                        raise RuntimeError("source-returned-html")
                disposition = headers.get("content-disposition", "")
                filename_match = re.search(
                    r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)", disposition, re.IGNORECASE,
                )
                response_name = unquote(next(
                    (group for group in filename_match.groups() if group), ""
                )) if filename_match else ""
                target = target_dir / safe_filename(response_name or fallback_name)
                temporary.replace(target)
                temporary = None
                result = {
                    "localPath": str(target), "status": "local", "errorCode": None,
                    "sizeBytes": target.stat().st_size, "mimeType": mime_type,
                    "captureMode": "browser-stream",
                }
                await session.send("Fetch.fulfillRequest", {
                    "requestId": request_id, "responseCode": 204, "body": "",
                    "responseHeaders": [{"name": "Content-Length", "value": "0"}],
                })
                if not finished.done():
                    finished.set_result(result)
            except Exception as exc:
                if not finished.done():
                    finished.set_exception(exc)
            finally:
                if stream_handle:
                    try:
                        await session.send("IO.close", {"handle": stream_handle})
                    except Exception:
                        pass
                if temporary:
                    temporary.unlink(missing_ok=True)

        def on_response(event: dict[str, Any]) -> None:
            task = asyncio.create_task(handle_response(event))
            handlers.add(task)
            task.add_done_callback(handlers.discard)

        session.on("Fetch.requestPaused", on_response)
        try:
            await session.send("Fetch.enable", {"patterns": [{
                "urlPattern": "*", "resourceType": "Document", "requestStage": "Response",
            }]})
            navigation = asyncio.create_task(
                download_page.goto(url, wait_until="commit", timeout=15_000)
            )
            # asyncio uses seconds; Playwright's timeout arguments use milliseconds.
            return await asyncio.wait_for(finished, timeout=timeout_seconds)
        except Exception as exc:
            if "target page, context or browser has been closed" in str(exc).lower():
                raise
            return None
        finally:
            if navigation:
                if not navigation.done():
                    navigation.cancel()
                try:
                    await navigation
                except (asyncio.CancelledError, Exception):
                    pass
            for task in handlers:
                task.cancel()
            # Closing the temporary page also detaches its CDP session. An
            # explicit detach can wait forever while a response body is paused.
            await download_page.close()

    async def _download_via_browser_navigation(
        self,
        page: Any,
        url: str,
        target_dir: Path,
        fallback_name: str,
    ) -> dict[str, Any] | None:
        target_dir.mkdir(parents=True, exist_ok=True)
        download_page = await page.context.new_page()
        try:
            async with download_page.expect_download(timeout=12_000) as pending:
                try:
                    await download_page.goto(url, wait_until="commit", timeout=12_000)
                except Exception as exc:
                    if "download is starting" not in str(exc).lower():
                        raise
            download = await pending.value
            target = target_dir / safe_filename(download.suggested_filename or fallback_name or "attachment")
            await download.save_as(str(target))
            if not target.is_file() or target.stat().st_size <= 0:
                raise RuntimeError("browser-download-empty")
            return {
                "localPath": str(target), "status": "local", "errorCode": None,
                "sizeBytes": target.stat().st_size,
                "mimeType": mimetypes.guess_type(target.name)[0],
                "captureMode": "browser-navigation",
            }
        except Exception:
            return None
        finally:
            await download_page.close()

    async def _download_attachment_fallbacks(
        self,
        page: Any,
        channel_id: str,
        messages: list[dict[str, Any]],
        results: dict[str, dict[str, Any]],
    ) -> None:
        """Fetch rendered SharePoint file URLs when their UI card cannot be driven."""
        for message in messages:
            message_id = message.get("id") or message_capture_key(message)
            for index, item in enumerate(message.get("attachments", [])):
                url = item.get("url") or ""
                cached = results.get(url)
                if cached and cached.get("status") == "local":
                    item.update({key: value for key, value in cached.items() if key != "attempts"})
                    continue
                attachment_id = stable_hash(message_id, url or f"{item.get('name', '')}:{index}")
                item.update({"id": attachment_id, "captureMode": "rendered-url"})
                target_dir = self.files_root / storage_key(channel_id) / attachment_id
                target_dir.mkdir(parents=True, exist_ok=True)
                existing = next(
                    (path for path in target_dir.iterdir() if path.is_file() and path.stat().st_size > 0),
                    None,
                )
                if existing:
                    result = {
                        "localPath": str(existing), "status": "local", "errorCode": None,
                        "sizeBytes": existing.stat().st_size,
                        "mimeType": mimetypes.guess_type(existing.name)[0],
                        "captureMode": "rendered-url",
                    }
                    results[url] = result
                    item.update(result)
                    continue

                parsed = urlparse(url)
                if not trusted_sharepoint_url(url):
                    result = {
                        "localPath": None, "status": "failed", "errorCode": "unsupported-file-host",
                        "attempts": 2, "captureMode": "rendered-url",
                    }
                    results[url] = result
                    item.update({key: value for key, value in result.items() if key != "attempts"})
                    continue

                if not self.avoid_browser_downloads:
                    navigation_result = await self._download_via_browser_navigation(
                        page, url, target_dir, item.get("name") or "attachment",
                    )
                    if navigation_result:
                        results[url] = navigation_result
                        item.update(navigation_result)
                        continue

                try:
                    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
                    query["download"] = "1"
                    download_url = urlunparse(parsed._replace(query=urlencode(query)))
                    response = None
                    body = b""
                    mime_type = "application/octet-stream"
                    last_error = "source-returned-html"
                    for candidate_url in dict.fromkeys((download_url, url)):
                        candidate = await page.context.request.get(candidate_url, timeout=30_000)
                        candidate_type = (
                            candidate.headers.get("content-type") or "application/octet-stream"
                        ).split(";", 1)[0]
                        if not candidate.ok:
                            last_error = f"source-http-{candidate.status}"
                            continue
                        if candidate_type in {"text/html", "application/xhtml+xml"}:
                            last_error = "source-returned-html"
                            continue
                        candidate_body = await candidate.body()
                        if not candidate_body:
                            last_error = "source-empty"
                            continue
                        response = candidate
                        body = candidate_body
                        mime_type = candidate_type
                        break
                    if response is None:
                        raise RuntimeError(last_error)
                    disposition = response.headers.get("content-disposition") or ""
                    filename_match = re.search(
                        r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)", disposition, re.IGNORECASE,
                    )
                    response_name = unquote(next(
                        (group for group in filename_match.groups() if group), ""
                    )) if filename_match else ""
                    url_name = unquote(Path(parsed.path).name)
                    target = target_dir / safe_filename(response_name or item.get("name") or url_name or "attachment")
                    target.write_bytes(body)
                    result = {
                        "localPath": str(target), "status": "local", "errorCode": None,
                        "sizeBytes": target.stat().st_size, "mimeType": mime_type,
                        "captureMode": "rendered-url",
                    }
                    results[url] = result
                    item.update(result)
                except Exception as exc:
                    error_code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                    result = {
                        "localPath": None, "status": "failed", "errorCode": error_code,
                        "attempts": 2, "captureMode": "rendered-url",
                    }
                    if cached and cached.get("errorCode"):
                        result["uiErrorCode"] = cached["errorCode"]
                    results[url] = result
                    item.update({key: value for key, value in result.items() if key != "attempts"})

    async def capture_channel(
        self,
        page: Any,
        identity: ChannelIdentity,
        completed: set[str],
        on_post: Callable[[dict[str, Any]], Awaitable[None]],
        pause_gate: Callable[[], Awaitable[None]],
    ) -> dict[str, int]:
        viewport = await self._channel_viewport(page)
        await viewport.evaluate("el => { el.scrollTop=el.scrollHeight; el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
        await asyncio.sleep(1.0)
        captured: set[str] = set()
        totals = {
            "posts": 0, "expectedReplies": 0, "capturedReplies": 0,
            "files": 0, "failedFiles": 0, "pendingFiles": 0, "uncertain": 0,
        }
        stable_rounds = 0
        for _ in range(60):
            summaries = await self._root_summaries(page)
            added = 0
            for summary in summaries:
                post_id = summary.get("id")
                if not post_id or post_id in captured:
                    continue
                captured.add(post_id)
                if post_id in completed:
                    continue
                await pause_gate()
                expected = int(summary.get("expectedReplies") or 0)
                messages: list[dict[str, Any]] = []
                stable = 0
                download_results: dict[str, dict[str, Any]] = {}
                asset_results: dict[str, dict[str, Any]] = {}
                if expected and summary.get("hasReplyButton"):
                    root_candidates = await self._extract_messages(page, f"#reply-chain-summary-{post_id}")
                    root_message = next(
                        (message for message in root_candidates if message.get("id") == post_id),
                        root_candidates[0] if root_candidates else None,
                    )
                    if root_message is None:
                        raise RuntimeError("root-message-not-found")
                    await self._save_assets(page, identity.id, [root_message], asset_results)
                    await self._download_attachments(page, identity.id, [root_message], download_results)
                    for _attempt in range(3):
                        root = page.locator(f"#reply-chain-summary-{post_id}")
                        await root.locator('[data-tid="response-summary-button"]').click(timeout=10_000)
                        messages, stable = await self._load_thread(
                            page, identity.id, post_id, root_message, expected,
                            download_results, asset_results,
                        )
                        if len(messages) - 1 == expected:
                            break
                        await page.locator('[data-tid="close-l2-view-button"]').click()
                        await asyncio.sleep(0.5)
                    if await page.locator('[data-tid="close-l2-view-button"]').count():
                        await page.locator('[data-tid="close-l2-view-button"]').click()
                        await asyncio.sleep(0.5)
                elif expected:
                    messages = await self._extract_inline_messages(page, post_id)
                    await self._save_assets(page, identity.id, messages, asset_results)
                    await self._download_attachments(page, identity.id, messages, download_results)
                    await self._download_attachment_fallbacks(
                        page, identity.id, messages, download_results,
                    )
                else:
                    root = page.locator(f"#reply-chain-summary-{post_id}")
                    messages = await self._extract_messages(page, f"#reply-chain-summary-{post_id}")
                    await self._save_assets(page, identity.id, messages, asset_results)
                    await self._download_attachments(page, identity.id, messages, download_results)
                    await self._download_attachment_fallbacks(
                        page, identity.id, messages, download_results,
                    )
                attachments = [item for message in messages for item in message.get("attachments", [])]
                files = sum(item.get("status") == "local" for item in attachments)
                failed_files = sum(item.get("status") == "failed" for item in attachments)
                pending_files = sum(item.get("status", "pending") == "pending" for item in attachments)
                captured_replies = max(0, len(messages) - 1)
                matches = captured_replies == expected
                post = {"id": post_id, "expectedReplies": expected, "capturedReplies": captured_replies,
                        "countMatches": matches, "stableRounds": stable, "messages": messages}
                await on_post(post)
                totals["posts"] += 1
                totals["expectedReplies"] += expected
                totals["capturedReplies"] += captured_replies
                totals["files"] += files
                totals["failedFiles"] += failed_files
                totals["pendingFiles"] += pending_files
                totals["uncertain"] += int(not matches)
                added += 1
            stable_rounds = stable_rounds + 1 if added == 0 else 0
            metrics = await viewport.evaluate("el => ({top:el.scrollTop, height:el.scrollHeight, client:el.clientHeight})")
            if stable_rounds >= 3 and metrics["top"] <= 1:
                break
            await viewport.evaluate("el => { el.scrollTop=Math.max(0,el.scrollTop-Math.max(500,el.clientHeight*.8)); el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
            await asyncio.sleep(0.9)
        return totals
