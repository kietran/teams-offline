from unittest.mock import AsyncMock, Mock

import pytest
from playwright.async_api import Error

from teams_archive.capture.browser import ChromeSessionManager


@pytest.mark.asyncio
async def test_status_handles_close_between_check_and_dom_read(tmp_path):
    manager = ChromeSessionManager(tmp_path)
    page = Mock()
    page.is_closed.return_value = False
    page.url = "https://teams.cloud.microsoft/"
    page.locator.return_value.count = AsyncMock(
        side_effect=Error("Target page, context or browser has been closed")
    )
    manager._context = Mock()
    manager._teams_page = page
    state = await manager.status()
    assert not state.running
    assert not state.signed_in
    assert manager._teams_page is page


@pytest.mark.asyncio
async def test_status_does_not_hide_other_errors(tmp_path):
    manager = ChromeSessionManager(tmp_path)
    page = Mock()
    page.is_closed.return_value = False
    page.url = "https://teams.cloud.microsoft/"
    page.locator.return_value.count = AsyncMock(side_effect=Error("unexpected protocol failure"))
    manager._context = Mock()
    manager._teams_page = page
    with pytest.raises(Error, match="unexpected protocol failure"):
        await manager.status()
