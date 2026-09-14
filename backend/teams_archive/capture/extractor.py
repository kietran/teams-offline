from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from .models import ChannelIdentity


FORBIDDEN_ACTION_NAMES = {"send", "share", "edit", "delete", "reply in thread"}


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(" .")
    return cleaned[:180] or "attachment"


def team_from_title(page_title: str, channel_name: str) -> str:
    parts = [part.strip() for part in page_title.split("|")]
    if len(parts) >= 4 and parts[0].startswith("Teams"):
        return parts[-3]
    return "Teams"


class TeamsDomExtractor:
    def __init__(self, files_root: Path, assets_root: Path) -> None:
        self.files_root = files_root
        self.assets_root = assets_root

    async def navigate_to_channel(self, page: Any, team_name: str, channel_name: str) -> None:
        current_node = page.locator('[data-tid="channelTitle-text"]')
        current = await current_node.first.text_content(timeout=1_000) if await current_node.count() else None
        if current and current.strip() == channel_name:
            return
        tree_items = page.get_by_role("treeitem").filter(has_text=channel_name)
        for index in range(await tree_items.count()):
            item = tree_items.nth(index)
            label = await item.get_attribute("aria-label") or ""
            if team_name in label or await tree_items.count() == 1:
                await item.click(timeout=10_000)
                await page.locator('[data-tid="channelTitle-text"]').filter(has_text=channel_name).wait_for(timeout=15_000)
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
        return await page.evaluate(r"""selector => [...document.querySelectorAll(selector)].map((el, index) => {
          const clean = value => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').trim();
          const body = el.querySelector('[data-tid="message-body"]');
          const id = body?.id?.match(/content-(\d{10,})/)?.[1] || null;
          const avatar = el.querySelector('[data-tid="post-message-header-avatar"][aria-label], [data-tid="reply-message-header-avatar"][aria-label]');
          const explicit = el.querySelector('time[data-tid="timestamp"]')?.getAttribute('aria-label') || null;
          const attachments = []; const seen = new Set();
          for (const node of el.querySelectorAll('[aria-label*="http"]')) {
            const label = node.getAttribute('aria-label') || ''; const match = label.match(/https?:\/\/\S+/);
            if (!match) continue; const url = match[0]; const name = clean(label.slice(0, match.index));
            if (!seen.has(url)) { seen.add(url); attachments.push({name, url}); }
          }
          return {id, order:index, author:(avatar?.getAttribute('aria-label') || '').replace(/^Profile picture of /,'').replace(/\.$/, '') || null,
            timestamp:id && /^\d{13}$/.test(id) ? new Date(Number(id)).toISOString() : explicit,
            timestampLabel:explicit, subject:clean(el.querySelector('[data-tid="subject-line"]')?.textContent),
            text:el.querySelector('[data-tid="message-tombstone"]') ? '[This message has been deleted.]' : clean(body?.innerText),
            html:el.querySelector('[data-tid="message-tombstone"]') ? '' : (body?.innerHTML || ''),
            deleted:Boolean(el.querySelector('[data-tid="message-tombstone"]')), attachments,
            images:[...body?.querySelectorAll('img') || []].map(img => ({alt:img.alt || '', src:img.src || ''}))};
        })""", selector)

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
            for (const node of el.querySelectorAll('[aria-label*="http"]')) {
              const label=node.getAttribute('aria-label')||''; const match=label.match(/https?:\/\/\S+/);
              if(match&&!seen.has(match[0])){seen.add(match[0]);attachments.push({name:clean(label.slice(0,match.index)),url:match[0]});}
            }
            return {id,order:index,author:(avatar?.getAttribute('aria-label')||'').replace(/^Profile picture of /,'').replace(/\.$/,'')||null,
              timestamp:id&&/^\d{13}$/.test(id)?new Date(Number(id)).toISOString():explicit,timestampLabel:explicit,
              subject:index===0?clean(root.querySelector('[data-tid="subject-line"]')?.textContent):'',text:clean(body.innerText),html:body.innerHTML||'',deleted:false,attachments,
              images:[...body.querySelectorAll('img')].map(img=>({alt:img.alt||'',src:img.src||''}))};
          });
        }""", post_id)

    async def _load_thread(self, page: Any) -> tuple[list[dict[str, Any]], int]:
        viewport = page.locator('[data-tid="channel-replies-viewport"]')
        await viewport.wait_for(state="visible", timeout=15_000)
        previous = -1
        stable = 0
        for _ in range(16):
            await viewport.evaluate("el => { el.scrollTop=0; el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
            await asyncio.sleep(0.65)
            count = await page.locator('[data-tid="channel-replies-pane-message"]').count()
            stable = stable + 1 if count == previous else 0
            previous = count
            if stable >= 3:
                break
        return await self._extract_messages(page, '[data-tid="channel-replies-pane-message"]'), stable

    async def _save_assets(self, page: Any, channel_id: str, messages: list[dict[str, Any]]) -> None:
        for message in messages:
            message_id = message.get("id") or stable_hash(channel_id, str(message.get("order")))[:24]
            saved = []
            for index, image in enumerate(message.get("images", [])):
                src = image.get("src") or ""
                asset_id = stable_hash(message_id, src or str(index))
                target_dir = self.assets_root / channel_id
                target_dir.mkdir(parents=True, exist_ok=True)
                stored = None
                capture_mode = "original"
                mime_type = None
                if src.startswith("http"):
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
                    saved.append({**image, "id": asset_id, "localPath": str(stored), "sizeBytes": stored.stat().st_size,
                                  "mimeType": mime_type, "captureMode": capture_mode})
            message["images"] = saved

    async def _download_attachments(self, page: Any, channel_id: str, messages: list[dict[str, Any]]) -> tuple[int, int]:
        by_url = {item["url"]: item for message in messages for item in message.get("attachments", []) if item.get("url")}
        by_id = {message.get("id"): message for message in messages if message.get("id")}
        action_buttons = page.locator('[data-tid="file-attachment-grid"]').get_by_role(
            "button", name="More actions"
        )
        downloaded = 0
        for index in range(await action_buttons.count()):
            more = action_buttons.nth(index)
            group = more.locator("xpath=ancestor::*[@role='group'][1]")
            metadata = await group.evaluate(r"""el => {
              const label=el.getAttribute('aria-label')||'';
              const nested=[...el.querySelectorAll('[aria-label*="http"]')].map(node=>node.getAttribute('aria-label')||'');
              const source=[label,...nested].find(value=>/https?:\/\//.test(value))||'';
              const url=source.match(/https?:\/\/\S+/)?.[0]||null;
              let current=el.parentElement; let messageId=null;
              while(current&&!messageId){const bodies=current.querySelectorAll('[data-tid="message-body"]');if(bodies.length===1)messageId=bodies[0].id?.match(/content-(\d{10,})/)?.[1]||null;current=current.parentElement;}
              return {name:label.trim(),url,messageId};
            }""")
            name = metadata.get("name") or "attachment"
            url = metadata.get("url")
            message = by_id.get(metadata.get("messageId")) or (messages[0] if messages else None)
            if not message:
                continue
            item = by_url.get(url) if url else next(
                (entry for entry in message.get("attachments", []) if entry.get("name") == name), None
            )
            if not item:
                item = {"name": name, "url": url}
                message.setdefault("attachments", []).append(item)
            attachment_id = stable_hash(message.get("id") or "", url or f"{name}:{index}")
            item.update({"id": attachment_id, "captureMode": "download"})
            target_dir = self.files_root / channel_id / attachment_id
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                await more.click(timeout=8_000)
                async with page.expect_download(timeout=20_000) as pending:
                    await page.get_by_role("menuitem", name="Download").click(timeout=8_000)
                download = await pending.value
                target = target_dir / safe_filename(download.suggested_filename or name)
                await download.save_as(str(target))
                item.update({"localPath": str(target), "status": "local", "errorCode": None})
                downloaded += 1
            except Exception as exc:
                item.update({"localPath": None, "status": "failed", "errorCode": type(exc).__name__})
                await page.keyboard.press("Escape")
        for message in messages:
            for item in message.get("attachments", []):
                item.setdefault("id", stable_hash(message.get("id") or "", item.get("url") or item.get("name") or ""))
                item.setdefault("status", "pending")
                item.setdefault("captureMode", "download")
        failed = sum(
            item.get("status") != "local"
            for message in messages
            for item in message.get("attachments", [])
        )
        return downloaded, failed

    async def capture_channel(
        self,
        page: Any,
        identity: ChannelIdentity,
        completed: set[str],
        on_post: Callable[[dict[str, Any]], Awaitable[None]],
        pause_gate: Callable[[], Awaitable[None]],
    ) -> dict[str, int]:
        viewport = page.locator('[data-tid="channel-pane-viewport"]')
        await viewport.wait_for(state="visible", timeout=15_000)
        await viewport.evaluate("el => { el.scrollTop=el.scrollHeight; el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
        await asyncio.sleep(1.0)
        captured: set[str] = set()
        totals = {"posts": 0, "expectedReplies": 0, "capturedReplies": 0, "files": 0, "failedFiles": 0, "uncertain": 0}
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
                if expected and summary.get("hasReplyButton"):
                    for _attempt in range(3):
                        root = page.locator(f"#reply-chain-summary-{post_id}")
                        await root.locator('[data-tid="response-summary-button"]').click(timeout=10_000)
                        messages, stable = await self._load_thread(page)
                        if len(messages) - 1 == expected:
                            break
                        await page.locator('[data-tid="close-l2-view-button"]').click()
                        await asyncio.sleep(0.5)
                    await self._save_assets(page, identity.id, messages)
                    files, failed_files = await self._download_attachments(page, identity.id, messages)
                    if await page.locator('[data-tid="close-l2-view-button"]').count():
                        await page.locator('[data-tid="close-l2-view-button"]').click()
                        await asyncio.sleep(0.5)
                elif expected:
                    messages = await self._extract_inline_messages(page, post_id)
                    await self._save_assets(page, identity.id, messages)
                    files, failed_files = await self._download_attachments(page, identity.id, messages)
                else:
                    root = page.locator(f"#reply-chain-summary-{post_id}")
                    messages = await self._extract_messages(page, f"#reply-chain-summary-{post_id}")
                    await self._save_assets(page, identity.id, messages)
                    files, failed_files = await self._download_attachments(page, identity.id, messages)
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
                totals["uncertain"] += int(not matches)
                added += 1
            stable_rounds = stable_rounds + 1 if added == 0 else 0
            metrics = await viewport.evaluate("el => ({top:el.scrollTop, height:el.scrollHeight, client:el.clientHeight})")
            if stable_rounds >= 3 and metrics["top"] <= 1:
                break
            await viewport.evaluate("el => { el.scrollTop=Math.max(0,el.scrollTop-Math.max(500,el.clientHeight*.8)); el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
            await asyncio.sleep(0.9)
        return totals
