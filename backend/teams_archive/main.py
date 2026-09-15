from __future__ import annotations

import threading
import webbrowser
import os
import sys
from pathlib import Path

import uvicorn

from .api import create_app
from .config import DEFAULT_PORT, LOOPBACK_HOST


def main() -> None:
    if "--self-test" in sys.argv:
        import asyncio

        from playwright.async_api import async_playwright

        async def test_playwright_driver() -> None:
            driver = await async_playwright().start()
            await driver.stop()

        asyncio.run(test_playwright_driver())
        return
    if getattr(sys, "frozen", False):
        frontend_dist = Path(getattr(sys, "_MEIPASS")) / "frontend_dist"
    else:
        frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if os.getenv("TEAMS_ARCHIVE_NO_OPEN") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{LOOPBACK_HOST}:{DEFAULT_PORT}")).start()
    uvicorn.run(
        create_app(frontend_dist=frontend_dist),
        host=LOOPBACK_HOST,
        port=DEFAULT_PORT,
        log_config=None,
        loop="asyncio",
        http="h11",
        ws="none",
    )


if __name__ == "__main__":
    main()
