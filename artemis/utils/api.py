from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import aiohttp


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
