from __future__ import annotations
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING
import httpx

from artemis.utils.common import ArtemisError

if TYPE_CHECKING:
    from ..bot import Artemis


class DeepLError(ArtemisError):
    pass


@dataclass
class Translation:
    src: str
    translation: str
    billed_characters: int


@dataclass
class Usage:
    character_count: int
    character_limit: int


class DeepL:
    API_URL = "https://api-free.deepl.com/v2"
    session: httpx.AsyncClient
    api_key: str
    headers: dict[str, str]
    over_quota: bool = False

    def __init__(self, bot: Artemis, api_key: str):
        self.session = bot.httpx_session
        self.api_key = api_key
        self.headers = {
            "User-Agent": bot.real_user_agent,
            "Authorization": f"DeepL-Auth-Key {api_key}",
        }

    async def translate(
        self, text: str, source_lang: str | None = None, target_lang="en"
    ) -> Translation:
        if self.over_quota:
            raise DeepLError("DeepL API quota exceeded.")

        url = f"{self.API_URL}/translate"
        data = {
            "text": [text],
            "target_lang": target_lang,
            "formality": "prefer_less",
            "show_billed_characters": True,
        }

        if source_lang and source_lang.lower() != "auto":
            data["source_lang"] = source_lang

        r = await self.session.post(url, json=data, headers=self.headers)
        if not r.is_success:
            if r.status_code == 456:
                self.over_quota = True
                raise DeepLError("DeepL API quota exceeded.")
            raise DeepLError(f"DeepL API returned an error: {r.status_code} {r.reason_phrase}")

        data = r.json()
        if not data["translations"]:
            raise DeepLError("DeepL API returned no translations.")

        result = data["translations"][0]
        translation = result["text"]
        source_lang = result.get("detected_source_language") or source_lang
        billed_characters = result["billed_characters"]

        return Translation(source_lang, translation, billed_characters)

    async def usage(self) -> Usage:
        url = f"{self.API_URL}/usage"
        r = await self.session.get(url, headers=self.headers)
        if not r.is_success:
            raise DeepLError(f"DeepL API returned an error: {r.status_code} {r.reason_phrase}")

        data = r.json()
        return Usage(**data)

    @cached_property
    def languages(self):
        return {
            "bg": "Bulgarian",
            "cs": "Czech",
            "da": "Danish",
            "de": "German",
            "el": "Greek",
            "en": "English",
            "es": "Spanish",
            "et": "Estonian",
            "fi": "Finnish",
            "fr": "French",
            "hu": "Hungarian",
            "id": "Indonesian",
            "it": "Italian",
            "ja": "Japanese",
            "ko": "Korean",
            "lt": "Lithuanian",
            "lv": "Latvian",
            "nb": "Norwegian",
            "nl": "Dutch",
            "pl": "Polish",
            "pt": "Portuguese",
            "ro": "Romanian",
            "ru": "Russian",
            "sk": "Slovak",
            "sl": "Slovenian",
            "sv": "Swedish",
            "tr": "Turkish",
            "uk": "Ukrainian",
            "zh": "Chinese",
        }
