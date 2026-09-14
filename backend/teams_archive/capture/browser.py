from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import ChromeState

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright


TEAMS_URL = "https://teams.cloud.microsoft/"


def chrome_executable() -> str | None:
    candidates = ["google-chrome-stable", "google-chrome", "chrome"]
    if sys.platform == "win32":
        candidates = ["chrome.exe", *candidates]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    if sys.platform == "win32":
        import os

        for base in filter(None, [os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"), os.getenv("LOCALAPPDATA")]):
            path = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if path.is_file():
                return str(path)
    return None


class ChromeSessionManager:
    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = profile_dir
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._teams_page: Page | None = None

    @property
    def installed(self) -> bool:
        return chrome_executable() is not None

    async def open(self) -> ChromeState:
        if self._context and self._teams_page and not self._teams_page.is_closed():
            await self._teams_page.bring_to_front()
            return await self.status()
        if not self.installed:
            raise RuntimeError("chrome-not-installed")
        from playwright.async_api import async_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel="chrome",
            headless=False,
            accept_downloads=True,
            viewport={"width": 1440, "height": 900},
        )
        pages = [page for page in self._context.pages if "teams." in page.url]
        self._teams_page = pages[0] if pages else await self._context.new_page()
        if not pages:
            await self._teams_page.goto(TEAMS_URL, wait_until="domcontentloaded")
        await self._teams_page.bring_to_front()
        return await self.status()

    async def page(self) -> Page:
        if not self._context or not self._teams_page or self._teams_page.is_closed():
            await self.open()
        assert self._teams_page is not None
        return self._teams_page

    async def status(self) -> ChromeState:
        running = bool(self._context and self._teams_page and not self._teams_page.is_closed())
        if not running:
            return ChromeState(self.installed, False, False, False)
        assert self._teams_page is not None
        url = self._teams_page.url
        login = "login.microsoftonline.com" in url or "login.live.com" in url
        signed_in = not login and await self._teams_page.locator('[data-tid="experience-layout"]').count() > 0
        current = None
        if signed_in:
            title_node = self._teams_page.locator('[data-tid="channelTitle-text"]')
            if await title_node.count():
                title = await title_node.first.text_content(timeout=1_000)
                if title:
                    current = {"displayName": title.strip(), "pageTitle": await self._teams_page.title()}
        return ChromeState(self.installed, True, signed_in, login, current)

    async def close(self) -> None:
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._context = None
        self._playwright = None
        self._teams_page = None
