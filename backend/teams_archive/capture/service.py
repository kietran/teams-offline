from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import nh3

from ..db import ArchiveDatabase
from .browser import ChromeSessionManager
from .extractor import TeamsDomExtractor


ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "a", "blockquote", "code", "pre", "span"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title", "target"}, "span": {"title"}}


def sanitize_post(post: dict[str, Any]) -> dict[str, Any]:
    for message in post.get("messages", []):
        message["html"] = nh3.clean(
            message.get("html") or "",
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes={"http", "https", "mailto"},
        )
    return post


class CaptureCoordinator:
    def __init__(self, database: ArchiveDatabase, browser: ChromeSessionManager, extractor: TeamsDomExtractor) -> None:
        self.database = database
        self.browser = browser
        self.extractor = extractor
        self._task: asyncio.Task[None] | None = None
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._pause_requested = False

    @property
    def active(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self, channel_ids: list[str] | None = None) -> str:
        if self.active:
            raise RuntimeError("capture-already-active")
        channels = self.database.list_channels()
        selected = channel_ids or [channel["id"] for channel in channels]
        known = {channel["id"] for channel in channels}
        selected = [channel_id for channel_id in selected if channel_id in known]
        if not selected:
            raise RuntimeError("no-selected-channels")
        run_id = self.database.create_capture_run(selected)
        self._pause_requested = False
        self._resume_event.set()
        self._task = asyncio.create_task(self._run(run_id), name=f"capture-{run_id}")
        return run_id

    async def pause(self, run_id: str) -> None:
        current = self.database.current_capture()
        if not current or current["id"] != run_id or current["status"] not in {"queued", "running"}:
            raise RuntimeError("capture-not-running")
        self._pause_requested = True
        self._resume_event.clear()

    async def resume(self, run_id: str) -> None:
        current = self.database.current_capture()
        if not current or current["id"] != run_id or current["status"] not in {"paused", "interrupted", "running"}:
            raise RuntimeError("capture-not-resumable")
        self._pause_requested = False
        self._resume_event.set()
        if not self.active:
            self._task = asyncio.create_task(self._run(run_id), name=f"capture-{run_id}")

    async def _pause_gate(self, run_id: str) -> None:
        if self._pause_requested:
            self.database.update_run(run_id, "paused")
        await self._resume_event.wait()
        current = self.database.current_capture()
        if current and current["id"] == run_id and current["status"] == "paused":
            self.database.update_run(run_id, "running", current_channel_id=current.get("current_channel_id"))

    async def _run(self, run_id: str) -> None:
        failures = 0
        totals = {"channels": 0, "posts": 0, "expectedReplies": 0, "capturedReplies": 0, "files": 0, "failedFiles": 0, "uncertain": 0}
        try:
            page = await self.browser.page()
            self.database.update_run(run_id, "running")
            for channel_id in self.database.capture_channel_ids(run_id):
                await self._pause_gate(run_id)
                channel = self.database.get_channel(channel_id)
                self.database.update_run(run_id, "running", current_channel_id=channel_id)
                self.database.update_channel_run(run_id, channel_id, status="running")
                try:
                    await self.extractor.navigate_to_channel(page, channel["team_name"], channel["display_name"])
                    completed = self.database.completed_post_ids(run_id)
                    counters = {"posts": 0, "expected": 0, "captured": 0, "files": 0}

                    async def on_post(post: dict[str, Any]) -> None:
                        sanitized = sanitize_post(post)
                        self.database.upsert_post(run_id, channel_id, sanitized)
                        counters["posts"] += 1
                        counters["expected"] += post.get("expectedReplies", 0)
                        counters["captured"] += post.get("capturedReplies", 0)
                        counters["files"] += sum(
                            item.get("status") == "local"
                            for message in post.get("messages", [])
                            for item in message.get("attachments", [])
                        )
                        self.database.update_channel_run(
                            run_id, channel_id, status="running", posts_seen=counters["posts"],
                            posts_completed=counters["posts"], expected_replies=counters["expected"],
                            captured_replies=counters["captured"], files_captured=counters["files"],
                        )

                    result = await self.extractor.capture_channel(
                        page, await self.extractor.discover_current_channel(page), completed, on_post,
                        lambda: self._pause_gate(run_id),
                    )
                    channel_status = "partial" if result["uncertain"] or result["failedFiles"] else "completed"
                    self.database.update_channel_run(
                        run_id, channel_id, status=channel_status,
                        error_code="attachment-failures" if result["failedFiles"] else None,
                        error_message=f"{result['failedFiles']} tệp cần thử lại." if result["failedFiles"] else None,
                    )
                    with self.database.connect() as connection:
                        connection.execute(
                            "UPDATE channels SET last_capture_status=?, last_captured_at=? WHERE id=?",
                            (channel_status, datetime.now(timezone.utc).isoformat(), channel_id),
                        )
                    totals["channels"] += 1
                    for key in ("posts", "expectedReplies", "capturedReplies", "files", "failedFiles", "uncertain"):
                        totals[key] += result[key]
                    failures += int(channel_status == "partial")
                except Exception as exc:
                    failures += 1
                    self.database.update_channel_run(
                        run_id, channel_id, status="failed", error_code=type(exc).__name__,
                        error_message=str(exc)[:300],
                    )
            final_status = "partial" if failures else "completed"
            self.database.update_run(run_id, final_status, summary=totals)
        except asyncio.CancelledError:
            self.database.update_run(run_id, "interrupted", summary=totals)
            raise
        except Exception as exc:
            self.database.update_run(run_id, "failed", summary={**totals, "error": type(exc).__name__})

    async def shutdown(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.browser.close()
