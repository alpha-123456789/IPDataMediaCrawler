# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/kuaishou/core.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


import asyncio
import os
# import random  # Removed as we now use fixed config.CRAWLER_MAX_SLEEP_SEC intervals
from asyncio import Task
from typing import Dict, List, Optional, Tuple

import httpx
from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from model.m_kuaishou import VideoUrlInfo, CreatorUrlInfo
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import kuaishou as kuaishou_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from tools.crawl_dedup import (
    filter_uncrawled_note_ids,
)
from tools.crawl_progress import emit_keyword_completed
from var import crawler_type_var, source_keyword_var

from .client import KuaiShouClient
from .exception import DataFetchError
from .help import (
    KS_SIGN_CAPTURE_SCRIPT,
    parse_video_info_from_url,
    parse_creator_info_from_url,
)
from .login import KuaishouLogin


class KuaishouCrawler(AbstractCrawler):
    context_page: Page
    ks_client: KuaiShouClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self):
        self.index_url = "https://www.kuaishou.com"
        self.cookie_urls = [self.index_url]
        self.user_agent = utils.get_user_agent()
        self.cdp_manager = None
        self.ip_proxy_pool = None  # Proxy IP pool, used for automatic proxy refresh

    async def start(self):
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(
                config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
            )
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(
                ip_proxy_info
            )

        async with async_playwright() as playwright:
            # Select startup mode based on configuration
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[KuaishouCrawler] Launching browser using CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[KuaishouCrawler] Launching browser using standard mode")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium, None, self.user_agent, headless=config.HEADLESS
                )
                # stealth.min.js is a js script to prevent the website from detecting the crawler.
                await self.browser_context.add_init_script(path="libs/stealth.min.js")


            self.context_page = await self.browser_context.new_page()
            await self.context_page.add_init_script(KS_SIGN_CAPTURE_SCRIPT)
            await self.context_page.goto(f"{self.index_url}?isHome=1")

            # Create a client to interact with the kuaishou website.
            self.ks_client = await self.create_ks_client(httpx_proxy_format)
            await self._log_request_context("initial")
            if not await self.ks_client.pong():
                login_obj = KuaishouLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone=httpx_proxy_format,
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.ks_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=self.cookie_urls,
                )
                await self._log_request_context("after_login_cookie_sync")

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for videos and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_videos()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their videos and comments
                await self.get_creators_and_videos()
            else:
                pass

            utils.logger.info("[KuaishouCrawler.start] Kuaishou Crawler finished ...")

    async def search(self):
        utils.logger.info("[KuaishouCrawler.search] Begin search kuaishou keywords")
        ks_limit_count = 20
        if config.CRAWLER_MAX_NOTES_COUNT < ks_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = ks_limit_count
        start_page = config.START_PAGE

        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(
                f"[KuaishouCrawler.search] Current search keyword: {keyword}"
            )
            keyword_completed = True
            search_session_id = ""
            page = 1

            while (
                page - start_page + 1
            ) * ks_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[KuaishouCrawler.search] Skip page: {page}")
                    page += 1
                    continue

                utils.logger.info(
                    f"[KuaishouCrawler.search] search kuaishou keyword: {keyword}, "
                    f"page: {page}"
                )
                try:
                    videos_res = await self.ks_client.search_info_by_keyword_v2(
                        keyword=keyword,
                        pcursor=str(page),
                        search_session_id=search_session_id,
                    )
                except (DataFetchError, httpx.RequestError) as ex:
                    keyword_completed = False
                    utils.logger.error(
                        f"[KuaishouCrawler.search] keyword:{keyword}, page:{page} "
                        f"failed after retries: {ex}"
                    )
                    break

                if not videos_res or videos_res.get("result") != 1:
                    keyword_completed = False
                    utils.logger.error(
                        f"[KuaishouCrawler.search] search info by keyword:{keyword}, "
                        f"page:{page} returned unexpected result: {videos_res}"
                    )
                    break

                search_session_id = videos_res.get("searchSessionId", "")
                feeds = videos_res.get("feeds", [])
                candidate_ids = [
                    (video_detail.get("photo") or {}).get("id")
                    for video_detail in feeds
                ]
                candidate_ids = [video_id for video_id in candidate_ids if video_id]
                uncrawled_ids = set(
                    await filter_uncrawled_note_ids("ks", candidate_ids)
                )
                video_id_list: List[str] = []
                for video_detail in feeds:
                    photo = video_detail.get("photo") or {}
                    video_id = photo.get("id")
                    if video_id not in uncrawled_ids:
                        continue
                    await kuaishou_store.update_kuaishou_video(
                        video_item=video_detail
                    )
                    video_id_list.append(video_id)

                utils.logger.info(
                    f"[KuaishouCrawler.search] keyword:{keyword}, page:{page}, "
                    f"got {len(candidate_ids)} videos, saved {len(video_id_list)} new videos"
                )
                await self.batch_get_video_comments(video_id_list)
                page += 1
                if (
                    page - start_page + 1
                ) * ks_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

            if keyword_completed:
                emit_keyword_completed(config.PLATFORM, keyword)

    async def get_specified_videos(self):
        """Get the information and comments of the specified post"""
        utils.logger.info("[KuaishouCrawler.get_specified_videos] Parsing video URLs...")
        video_ids = []
        for video_url in config.KS_SPECIFIED_ID_LIST:
            try:
                video_info = parse_video_info_from_url(video_url)
                video_ids.append(video_info.video_id)
                utils.logger.info(f"Parsed video ID: {video_info.video_id} from {video_url}")
            except ValueError as e:
                utils.logger.error(f"Failed to parse video URL: {e}")
                continue

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_video_info_task(video_id=video_id, semaphore=semaphore)
            for video_id in video_ids
        ]
        video_details = await asyncio.gather(*task_list)
        for video_detail in video_details:
            if video_detail is not None:
                await kuaishou_store.update_kuaishou_video(video_detail)
        await self.batch_get_video_comments(video_ids)

    async def get_video_info_task(
        self, video_id: str, semaphore: asyncio.Semaphore
    ) -> Optional[Dict]:
        """Get video detail task"""
        async with semaphore:
            try:
                result = await self.ks_client.get_video_info(video_id)

                # Sleep after fetching video details
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[KuaishouCrawler.get_video_info_task] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching video details {video_id}")

                video_detail = result.get("visionVideoDetail")
                photo = video_detail.get("photo") if video_detail else None
                utils.logger.info(
                    "[KuaishouCrawler.get_video_info_task] Get video detail: "
                    f"requested_id={video_id}, returned_id={photo.get('id') if photo else None}, "
                    f"has_detail={bool(video_detail)}"
                )
                return video_detail
            except httpx.RequestError as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_video_info_task] Get video {video_id} detail "
                    f"failed after retries, skipping: {ex}"
                )
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_video_info_task] have not fund video detail video_id:{video_id}, err: {ex}"
                )
                return None
            except Exception as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_video_info_task] Video {video_id} detail "
                    f"failed, skipping: {ex}"
                )
                return None

    async def batch_get_video_comments(self, video_id_list: List[str]):
        """
        batch get video comments
        :param video_id_list:
        :return:
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                f"[KuaishouCrawler.batch_get_video_comments] Crawling comment mode is not enabled"
            )
            return

        utils.logger.info(
            f"[KuaishouCrawler.batch_get_video_comments] video ids:{video_id_list}"
        )
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for video_id in video_id_list:
            task = asyncio.create_task(
                self.get_comments(video_id, semaphore), name=video_id
            )
            task_list.append(task)

        await asyncio.gather(*task_list)

    async def get_comments(self, video_id: str, semaphore: asyncio.Semaphore):
        """
        get comment for video id
        :param video_id:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                utils.logger.info(
                    f"[KuaishouCrawler.get_comments] begin get video_id: {video_id} comments ..."
                )

                # Sleep before fetching comments
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[KuaishouCrawler.get_comments] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds before fetching comments for video {video_id}")

                await self.ks_client.get_video_all_comments(
                    photo_id=video_id,
                    crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                    callback=kuaishou_store.batch_update_ks_video_comments,
                    max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except httpx.RequestError as ex:
                utils.logger.error(
                    f"[KuaishouCrawler.get_comments] video_id: {video_id} comments "
                    f"failed after retries, skipping: {ex}"
                )
            except Exception as e:
                utils.logger.error(
                    f"[KuaishouCrawler.get_comments] video_id: {video_id} comments failed, skipping: {e}"
                )

    async def create_ks_client(self, httpx_proxy: Optional[str]) -> KuaiShouClient:
        """Create ks client"""
        utils.logger.info(
            "[KuaishouCrawler.create_ks_client] Begin create kuaishou API client ..."
        )
        # CDP may attach to an existing Chrome context, whose actual UA can differ
        # from the random UA generated before the connection was established.
        self.user_agent = await self.context_page.evaluate("() => navigator.userAgent")
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            self.browser_context,
            urls=self.cookie_urls,
        )
        ks_client_obj = KuaiShouClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": self.index_url,
                "Referer": self.index_url,
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,  # Pass proxy pool for automatic refresh
        )
        return ks_client_obj

    async def _log_request_context(self, stage: str) -> None:
        """Log non-sensitive browser and HTTP session metadata for diagnosis."""
        browser_user_agent = ""
        try:
            browser_user_agent = await self.context_page.evaluate(
                "() => navigator.userAgent"
            )
        except Exception as ex:
            utils.logger.warning(
                f"[KuaishouCrawler] Unable to read browser User-Agent at {stage}: {ex}"
            )

        cookie_names = sorted(self.ks_client.cookie_dict)
        utils.logger.info(
            f"[KuaishouCrawler] Request context ({stage}): "
            f"browser_user_agent={browser_user_agent!r}, "
            f"http_user_agent={self.ks_client.headers.get('User-Agent', '')!r}, "
            f"cookie_names={cookie_names}, "
            f"has_pass_token={'passToken' in self.ks_client.cookie_dict}, "
            f"using_proxy={bool(self.ks_client.proxy)}"
        )

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info(
            "[KuaishouCrawler.launch_browser] Begin create browser context ..."
        )
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM
            )  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                channel="chrome",  # Use system's stable Chrome version
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy, channel="chrome")  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        Launch browser using CDP mode
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # Display browser information
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[KuaishouCrawler] CDP browser info: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(
                f"[KuaishouCrawler] CDP mode launch failed, fallback to standard mode: {e}"
            )
            # Fallback to standard mode
            chromium = playwright.chromium
            return await self.launch_browser(
                chromium, playwright_proxy, user_agent, headless
            )

    async def get_creators_and_videos(self) -> None:
        """Get creator's videos and retrieve their comment information."""
        utils.logger.info(
            "[KuaiShouCrawler.get_creators_and_videos] Begin get kuaishou creators"
        )
        for creator_url in config.KS_CREATOR_ID_LIST:
            try:
                # Parse creator URL to get user_id
                creator_info: CreatorUrlInfo = parse_creator_info_from_url(creator_url)
                utils.logger.info(f"[KuaiShouCrawler.get_creators_and_videos] Parse creator URL info: {creator_info}")
                user_id = creator_info.user_id

                # get creator detail info from web html content
                createor_info: Dict = await self.ks_client.get_creator_info(user_id=user_id)
                if createor_info:
                    await kuaishou_store.save_creator(user_id, creator=createor_info)

                # Get all video information of the creator
                all_video_list = await self.ks_client.get_all_videos_by_creator(
                    user_id=user_id,
                    crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                    callback=self.fetch_creator_video_detail,
                )
            except ValueError as e:
                utils.logger.error(f"[KuaiShouCrawler.get_creators_and_videos] Failed to parse creator URL: {e}")
                continue
            except httpx.RequestError as e:
                utils.logger.error(
                    f"[KuaiShouCrawler.get_creators_and_videos] Creator {creator_url} "
                    f"failed after retries, skipping: {e}"
                )
                continue

            video_ids = [
                video_item.get("photo", {}).get("id") for video_item in all_video_list
            ]
            await self.batch_get_video_comments(video_ids)

    async def fetch_creator_video_detail(self, video_list: List[Dict]):
        """
        Concurrently obtain the specified post list and save the data
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_video_info_task(post_item.get("photo", {}).get("id"), semaphore)
            for post_item in video_list
        ]

        video_details = await asyncio.gather(*task_list)
        for video_detail in video_details:
            if video_detail is not None:
                await kuaishou_store.update_kuaishou_video(video_detail)

    async def close(self):
        """Close browser context"""
        # If using CDP mode, need special handling
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[KuaishouCrawler.close] Browser context closed ...")
