from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import aiohttp

from .common import ArtemisError


if TYPE_CHECKING:
    from ..bot import Artemis


@dataclass
class DeepLResult:
    translation: str


class API:
    def __init__(self, bot: Artemis, token: str):
        self.base_url = "http://127.0.0.1:3000"
        self.token = token
        self.session: aiohttp.ClientSession = bot.session
        self.headers = {"User-Agent": bot.real_user_agent}
        self.authed_headers = {**self.headers, "Authorization": f"Bearer {self.token}"}

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
        headers = self.authed_headers if authed else self.headers
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
        wait_for_selector: str | None = None,
        wait_for_function: str | None = None,
    ) -> io.BytesIO:
        """Returns a PNG screenshot of the website at url with optional selector."""
        params = {"url": url}
        if selector:
            params["selector"] = selector
        if wait_for_selector:
            params["waitForSelector"] = wait_for_selector
        if wait_for_function:
            params["waitForFunction"] = wait_for_function

        res: bytes = await self._request(
            "GET", "/webdriver/screenshot", authed=True, res_type="bytes", params=params
        )
        return io.BytesIO(res)

    async def deepl(self, text: str, src: str = "auto", dst: str = "en") -> DeepLResult:
        """Returns DeepL translated text."""
        data = {"src": src.lower(), "dst": dst.lower(), "text": text}

        async with self.session.post(
            self.base_url + "/webdriver/deepl", json=data, headers=self.authed_headers
        ) as r:
            data = await r.json()
            if not r.ok:
                raise ArtemisError(f"DeepL Error: {data.get('error', 'Unknown')}")
            return DeepLResult(**data)
