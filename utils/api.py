from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from utils.common import ArtemisError

import aiohttp

if TYPE_CHECKING:
    from bot import Artemis


@dataclass
class DeepLResult:
    src: str
    dst: str
    translation: str


class API:
    def __init__(self, bot: Artemis, token: str):
        self.base_url = "http://127.0.0.1:3000"
        self.token = token
        self.session: aiohttp.ClientSession = bot.session
        self.HEADERS = {"User-Agent": bot.real_user_agent}
        self.AUTHED_HEADERS = {**self.HEADERS, "Authorization": f"Bearer {self.token}"}

    async def _aioread(self, fp):
        return await asyncio.to_thread(fp.read)

    async def _request(
        self,
        method: str,
        path: str,
        authed: bool = False,
        res_type: Literal["json", "text", "bytes"] = "json",
        **kwargs,
    ) -> Any:
        headers = self.AUTHED_HEADERS if authed else self.HEADERS
        async with self.session.request(
            method, self.base_url + path, headers=headers, **kwargs
        ) as r:
            match res_type:
                case "json":
                    return await r.json()
                case "text":
                    return await r.text()
                case "bytes":
                    return await r.read()

    async def screenshot(
        self,
        url: str,
        selector: str | None = None,
        waitForSelector: str | None = None,
        waitForFunction: str | None = None,
    ) -> io.BytesIO:
        """Returns a PNG screenshot of the website at url with optional selector."""
        params = {"url": url}
        if selector:
            params["selector"] = selector
        if waitForSelector:
            params["waitForSelector"] = waitForSelector
        if waitForFunction:
            params["waitForFunction"] = waitForFunction

        res: bytes = await self._request(
            "GET", "/webdriver/screenshot", authed=True, res_type="bytes", params=params
        )
        return io.BytesIO(res)

    async def deepl(self, text: str, src: str = "auto", dst: str = "en") -> DeepLResult:
        """Returns DeepL translated text."""
        data = {"src": src.lower(), "dst": dst.lower(), "text": text}

        async with self.session.post(
            self.base_url + "/webdriver/deepl", json=data, headers=self.AUTHED_HEADERS
        ) as r:
            data = await r.json()
            if not r.ok:
                raise ArtemisError(f"DeepL Error: `{data.get('error', 'Unknown')}`")
            return DeepLResult(**data)
