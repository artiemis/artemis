from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, TypeVar
from collections import deque
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from bot import Artemis

T = TypeVar("T")


class FeedNotifier:
    NAME: str = "Base"
    CHECK_INTERVAL: int | float = 60 * 5
    FEED_INTERVAL: int | float = 0.1
    CACHE_SIZE: int = 100

    bot: Artemis
    feeds: list[str]
    _cache = dict[str, list[str]]
    _task = asyncio.Task

    def __init__(self, bot: Artemis, feeds: list[str]):
        self.bot = bot
        self.feeds = feeds

        self._log = logging.getLogger(f"{self.NAME}Notifier")
        self._cache = {}
        for feed in self.feeds:
            self._cache[feed] = deque([], maxlen=self.CACHE_SIZE)

    def log(self, msg):
        self._log.info(msg)

    async def _run(self):
        try:
            await self._init_cache()
            await asyncio.sleep(self.CHECK_INTERVAL)
            self.log("Starting check loop...")
            while True:
                self.log("Processing feeds...")
                for feed in self.feeds:
                    entries = await self.fetch_entries(feed)
                    for entry in entries:
                        key = self.get_cache_key(entry)
                        if key in self._cache[feed]:
                            continue
                        self.log(f"{feed}: New entry found, handing over to on_new_entry()")
                        self._cache[feed].append(key)
                        await self.on_new_entry(entry)
                        await asyncio.sleep(self.FEED_INTERVAL)
                await asyncio.sleep(self.CHECK_INTERVAL)
        except Exception as error:
            await self.on_error(error)

    async def _init_cache(self):
        self.log("Bootstrapping cache...")
        for feed in self.feeds:
            self._cache[feed].extend(
                [self.get_cache_key(entry) for entry in await self.fetch_entries(feed)]
            )
            self.log(f"{feed}: Bootstrapped cache with {len(self._cache[feed])} entries.")

    def start(self):
        self._task = asyncio.create_task(self._run())
        self.log("Worker started.")
        return self

    def stop(self):
        try:
            self._task.cancel()
        except asyncio.CancelledError:
            pass
        finally:
            self.log("Worker stopped.")

    def get_cache_key(self, entry: T) -> str:
        raise NotImplementedError()

    async def fetch_entries(self, feed: str) -> list[T]:
        raise NotImplementedError()

    async def on_new_entry(self, entry: T):
        raise NotImplementedError()

    async def on_error(self, error: Exception):
        await self.send_to_user(
            self.bot.owner_id, f"[{self.NAME}Notifier] {error.__class__.__name__}: {str(error)}"
        )

    async def fetch_html(self, url):
        self.log(f"Fetching {url}")
        headers = {"User-Agent": self.bot.user_agent}
        async with self.bot.session.get(url, headers=headers) as r:
            html = await r.text()
        return BeautifulSoup(html, "lxml")

    async def fetch_json(self, url) -> dict:
        headers = {"User-Agent": self.bot.user_agent}
        async with self.bot.session.get(url, headers=headers) as r:
            return await r.json()

    async def send_to_channel(self, channel_id: int, *args, **kwargs):
        self.log(f"Sending new entry to channel {channel_id}.")
        await self.bot.get_channel(channel_id).send(*args, **kwargs)

    async def send_to_user(self, user_id: int, *args, **kwargs):
        self.log(f"Sending new entry to user {user_id}.")
        await self.bot.get_user(user_id).send(*args, **kwargs)


@dataclass
class HNEntry:
    title: str
    url: str


class HackerNewsNotifier(FeedNotifier):
    NAME = "HackerNews"
    CHECK_INTERVAL = 60

    def get_cache_key(self, entry: HNEntry) -> str:
        return entry.url

    async def fetch_entries(self, feed: str) -> list[HNEntry]:
        url = "https://news.ycombinator.com/" + feed
        soup = await self.fetch_html(url)

        articles = []
        for article in soup.select("tr.athing"):
            titleline = article.select_one("span.titleline > a")
            url = titleline["href"]
            title = titleline.text
            articles.append(HNEntry(title, url))
        return list(reversed(articles))

    async def on_new_entry(self, entry: HNEntry):
        await self.send_to_user(self.bot.owner_id, f"{entry.title}\n{entry.url}")
