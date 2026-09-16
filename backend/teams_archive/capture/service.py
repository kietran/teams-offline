from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import bleach

from ..db import ArchiveDatabase
from .browser import ChromeSessionManager
from .extractor import TeamsDomExtractor


ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "a", "blockquote", "code", "pre", "span"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title", "target"}, "span": {"title"}}
HTML_CLEANER = bleach.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    protocols={"http", "https", "mailto"},
    strip=True,
    strip_comments=True,
)


def sanitize_post(post: dict[str, Any]) -> dict[str, Any]:
    for message in post.get("messages", []):
        message["html"] = HTML_CLEANER.clean(message.get("html") or "")
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

    @staticmethod
    def _browser_was_closed(exc: Exception) -> bool:
        return type(exc).__name__ == "TargetClosedError" or "page, context or browser has been closed" in str(exc).lower()

    async def _capture_channel_once(self, run_id: str, channel_id: str, channel: dict[str, Any]) -> dict[str, int]:
        page = await self.browser.page()
        await self.extractor.navigate_to_channel(page, channel["team_name"], channel["display_name"])
        completed = self.database.completed_post_ids(run_id)
        progress = self.database.capture_channel_progress(run_id, channel_id)
        counters = {
            "posts": progress["posts_completed"],
            "expected": progress["expected_replies"],
            "captured": progress["captured_replies"],
            "files": progress["files_captured"],
            "failed_files": progress["files_failed"],
            "pending_files": progress["files_pending"],
        }

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
            counters["failed_files"] += sum(
                item.get("status") == "failed"
                for message in post.get("messages", [])
                for item in message.get("attachments", [])
            )
            counters["pending_files"] += sum(
                item.get("status", "pending") == "pending"
                for message in post.get("messages", [])
                for item in message.get("attachments", [])
            )
            self.database.update_channel_run(
                run_id, channel_id, status="running", posts_seen=counters["posts"],
                posts_completed=counters["posts"], expected_replies=counters["expected"],
                captured_replies=counters["captured"], files_captured=counters["files"],
                files_failed=counters["failed_files"], files_pending=counters["pending_files"],
            )

        identity = await self.extractor.discover_current_channel(page)
        await self.extractor.capture_channel(
            page, identity, completed, on_post, lambda: self._pause_gate(run_id),
        )
        current = self.database.capture_channel_progress(run_id, channel_id)
        return {
            "posts": current["posts_completed"],
            "expectedReplies": current["expected_replies"],
            "capturedReplies": current["captured_replies"],
            "files": current["files_captured"],
            "failedFiles": current["files_failed"],
            "pendingFiles": current["files_pending"],
            "uncertain": current["uncertain"],
        }

    async def _run(self, run_id: str) -> None:
        failures = 0
        totals = {
            "channels": 0, "posts": 0, "expectedReplies": 0, "capturedReplies": 0,
            "files": 0, "failedFiles": 0, "pendingFiles": 0, "uncertain": 0,
        }
        try:
            self.database.update_run(run_id, "running")
            for channel_id in self.database.capture_channel_ids(run_id):
                await self._pause_gate(run_id)
                channel = self.database.get_channel(channel_id)
                self.database.update_run(run_id, "running", current_channel_id=channel_id)
                self.database.update_channel_run(run_id, channel_id, status="running")
                try:
                    for attempt in range(2):
                        try:
                            result = await self._capture_channel_once(run_id, channel_id, channel)
                            break
                        except Exception as exc:
                            if attempt == 0 and self._browser_was_closed(exc):
                                await self.browser.reopen()
                                continue
                            raise
                    incomplete_files = result["failedFiles"] or result["pendingFiles"]
                    channel_status = "partial" if result["uncertain"] or incomplete_files else "completed"
                    file_message = None
                    if incomplete_files:
                        file_message = (
                            f"{result['failedFiles']} tệp tải lỗi · "
                            f"{result['pendingFiles']} tệp chưa được thử tải."
                        )
                    self.database.update_channel_run(
                        run_id, channel_id, status=channel_status,
                        files_failed=result["failedFiles"], files_pending=result["pendingFiles"],
                        error_code="attachment-incomplete" if incomplete_files else None,
                        error_message=file_message,
                    )
                    with self.database.connect() as connection:
                        connection.execute(
                            "UPDATE channels SET last_capture_status=?, last_captured_at=? WHERE id=?",
                            (channel_status, datetime.now(timezone.utc).isoformat(), channel_id),
                        )
                    totals["channels"] += 1
                    for key in (
                        "posts", "expectedReplies", "capturedReplies", "files",
                        "failedFiles", "pendingFiles", "uncertain",
                    ):
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
