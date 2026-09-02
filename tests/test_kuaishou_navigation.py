from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from media_platform.kuaishou.core import KuaishouCrawler


@pytest.mark.asyncio
async def test_kuaishou_homepage_navigation_waits_for_domcontentloaded():
    crawler = KuaishouCrawler()
    page = MagicMock()
    page.goto = AsyncMock()
    crawler.context_page = page

    await crawler._goto_homepage()

    page.set_default_navigation_timeout.assert_called_once_with(
        config.BROWSER_NAVIGATION_TIMEOUT
    )
    page.goto.assert_awaited_once_with(
        "https://www.kuaishou.com?isHome=1",
        wait_until="domcontentloaded",
        timeout=config.BROWSER_NAVIGATION_TIMEOUT,
    )
