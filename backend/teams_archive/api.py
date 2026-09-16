from __future__ import annotations

import os
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .capture.browser import ChromeSessionManager
from .capture.extractor import TeamsDomExtractor
from .capture.service import CaptureCoordinator
from .config import APP_NAME, AppConfig
from .db import ArchiveDatabase


class CaptureRequest(BaseModel):
    channelIds: list[str] | None = None


@dataclass
class AppServices:
    config: AppConfig
    database: ArchiveDatabase
    browser: Any
    coordinator: Any


def _open_local_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def create_app(
    config: AppConfig | None = None,
    browser: Any | None = None,
    coordinator: Any | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    resolved = config or AppConfig.from_env()
    resolved.paths.ensure()
    database = ArchiveDatabase(resolved.paths.database)
    database.initialize()
    browser_service = browser or ChromeSessionManager(resolved.paths.chrome_profile)
    capture_service = coordinator or CaptureCoordinator(
        database, browser_service, TeamsDomExtractor(resolved.paths.files, resolved.paths.assets)
    )
    services = AppServices(resolved, database, browser_service, capture_service)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        shutdown = getattr(capture_service, "shutdown", None)
        if shutdown:
            await shutdown()

    app = FastAPI(title=APP_NAME, version=__version__, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
    app.state.services = services

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        chrome = await browser_service.status()
        return {
            "setupComplete": bool(database.get_setting("setup_complete", False)),
            "chrome": chrome.api_dict() if hasattr(chrome, "api_dict") else chrome,
            "storage": {"mode": "local", "path": str(resolved.paths.root)},
            "selectedChannelCount": len(database.list_channels()),
            "capture": database.current_capture(),
        }

    @app.post("/api/chrome/open")
    async def open_chrome() -> dict[str, Any]:
        try:
            state = await browser_service.open()
            return state.api_dict() if hasattr(state, "api_dict") else state
        except RuntimeError as exc:
            if str(exc) == "chrome-not-installed":
                raise HTTPException(409, "Không tìm thấy Google Chrome Stable — hãy cài Chrome rồi thử lại.") from exc
            raise HTTPException(502, "Không thể mở Chrome — hãy đóng các cửa sổ thử nghiệm cũ rồi thử lại.") from exc

    @app.get("/api/chrome/status")
    async def chrome_status() -> dict[str, Any]:
        state = await browser_service.status()
        return state.api_dict() if hasattr(state, "api_dict") else state

    @app.post("/api/channels/current")
    async def add_current_channel() -> dict[str, Any]:
        try:
            page = await browser_service.page()
            identity = await capture_service.extractor.discover_current_channel(page)
            return database.upsert_channel(identity.api_dict())
        except RuntimeError as exc:
            if str(exc) == "not-on-channel":
                raise HTTPException(409, "Chrome chưa mở một kênh Teams — hãy mở kênh cần lưu rồi thử lại.") from exc
            raise HTTPException(502, "Không thể đọc kênh đang mở — hãy tải lại Teams rồi thử lại.") from exc

    @app.get("/api/channels")
    def channels() -> list[dict[str, Any]]:
        return database.list_channels()

    @app.delete("/api/channels/{channel_id}", status_code=204)
    def remove_channel(channel_id: str) -> None:
        if not database.deselect_channel(channel_id):
            raise HTTPException(404, "Không tìm thấy kênh đã chọn.")

    @app.post("/api/setup/complete")
    def complete_setup() -> dict[str, bool]:
        if not database.list_channels():
            raise HTTPException(409, "Hãy thêm ít nhất một kênh trước khi hoàn tất thiết lập.")
        database.set_setting("setup_complete", True)
        return {"setupComplete": True}

    @app.post("/api/storage/open", status_code=204)
    def open_storage() -> None:
        _open_local_path(resolved.paths.root)

    @app.post("/api/captures", status_code=202)
    async def start_capture(body: CaptureRequest) -> dict[str, str]:
        try:
            return {"id": await capture_service.start(body.channelIds)}
        except RuntimeError as exc:
            messages = {
                "capture-already-active": "Một quá trình lưu đang chạy — hãy tạm dừng hoặc chờ hoàn tất.",
                "no-selected-channels": "Chưa có kênh nào được chọn.",
            }
            raise HTTPException(409, messages.get(str(exc), "Không thể bắt đầu lưu dữ liệu.")) from exc

    @app.get("/api/captures/current")
    def current_capture() -> dict[str, Any] | None:
        return database.current_capture()

    @app.post("/api/captures/{run_id}/pause", status_code=202)
    async def pause_capture(run_id: str) -> dict[str, str]:
        try:
            await capture_service.pause(run_id)
            return {"status": "pause_requested"}
        except RuntimeError as exc:
            raise HTTPException(409, "Quá trình này không còn chạy.") from exc

    @app.post("/api/captures/{run_id}/resume", status_code=202)
    async def resume_capture(run_id: str) -> dict[str, str]:
        try:
            await capture_service.resume(run_id)
            return {"status": "running"}
        except RuntimeError as exc:
            raise HTTPException(409, "Quá trình này không thể tiếp tục.") from exc

    @app.get("/api/posts")
    def posts(
        query: str = "", channelId: str | None = None,
        cursor: str | None = None, limit: int = Query(50, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            offset = max(0, int(cursor or "0"))
            return database.list_posts(query, channelId, offset, limit)
        except ValueError as exc:
            raise HTTPException(400, "Cursor tìm kiếm không hợp lệ.") from exc
        except Exception as exc:
            raise HTTPException(400, "Từ khóa tìm kiếm không hợp lệ.") from exc

    @app.get("/api/posts/{root_id}")
    def post_detail(root_id: str) -> dict[str, Any]:
        result = database.get_post(root_id)
        if not result:
            raise HTTPException(404, "Không tìm thấy bài viết đã lưu.")
        return result

    @app.post("/api/attachments/{attachment_id}/open", status_code=204)
    def open_attachment(attachment_id: str) -> None:
        attachment = database.get_attachment(attachment_id)
        if not attachment or not attachment.get("local_cache_path"):
            raise HTTPException(404, "Tệp chưa có trên máy — hãy thử lưu lại channel.")
        path = Path(attachment["local_cache_path"]).resolve()
        if resolved.paths.files.resolve() not in path.parents or not path.is_file():
            raise HTTPException(404, "Tệp đã bị di chuyển hoặc xóa khỏi máy.")
        _open_local_path(path)

    if frontend_dist and frontend_dist.is_dir():
        assets = frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            candidate = (frontend_dist / path).resolve()
            if path and frontend_dist.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app
