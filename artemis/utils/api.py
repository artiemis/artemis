from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp

from artemis.utils.common import ArtemisError


if TYPE_CHECKING:
    from ..bot import Artemis


@dataclass
class YandexResult:
    text: str
    detected_lang: str | None = None


class API:
    def __init__(self, bot: Artemis, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.session: aiohttp.ClientSession = bot.session
        self.headers = {"User-Agent": bot.real_user_agent}
        self.authed_headers = {**self.headers, "Authorization": f"Bearer {self.token}"}

    async def yandex_ocr(self, image: bytes, mime: str):
        base64_image = base64.b64encode(image).decode("utf-8")
        data = {"file": base64_image, "mime": mime}

        async with self.session.post(
            self.base_url + "/ocr/yandex", json=data, headers=self.authed_headers
        ) as r:
            data = await r.json()
            if not r.ok:
                raise ArtemisError(f"Yandex Error: {data.get('error', 'Unknown')}")
            result = YandexResult(**data)
            if not result.text:
                raise ArtemisError("No text detected.")
            return result
