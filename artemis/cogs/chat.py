from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import aiohttp.client_exceptions
import discord
from discord.ext import commands
from huggingface_hub import AsyncInferenceClient

from artemis.utils import config


if TYPE_CHECKING:
    from ..bot import Artemis

log = logging.getLogger("artemis")


emoji_map = {
    "😀": ":D",
    "😃": ":D",
    "😄": ":D",
    "😁": ":D",
    "😆": ":D",
    "😅": ":D",
    "😂": ":'D",
    "🤣": ":'D",
    "😊": ":)",
    "😇": "^_^",
    "🙂": ":)",
    "😉": ";)",
    "😌": "-_-",
    "😍": "<3",
    "😘": ":-*",
    "😗": ":*",
    "😙": ":*",
    "😚": ":*",
    "😜": ";P",
    "😝": ":P",
    "😛": ":P",
    "🤑": "$-$",
    "🤗": "(hug)",
    "🤔": ":/",
    "😎": "8)",
    "😏": "^_^",
    "😒": "-_-",
    "😞": ":(",
    "😔": ":(",
    "😟": ":(",
    "😕": ":/",
    "🙁": ":(",
    "☹️": ":(",
    "😣": ":S",
    "😖": ":S",
    "😫": "DX",
    "😩": "DX",
    "😢": ":'(",
    "😭": ":'(",
    "😤": ">:(",
    "😠": ">:(",
    "😡": ">:(",
    "🤬": "#@!*&",
    "😈": ">:)",
    "👿": ">:)",
    "💀": "X_X",
    "☠️": "X_X",
    "😺": "=^_^=",
    "😸": "=^_^=",
    "😹": "=^_^=",
    "😻": "=^_^=",
    "😼": "-_-^",
    "😽": "=^_^=",
    "🙀": "=o_o=",
    "😿": "='(",
    "😾": "-_-^",
}

EMOJI_RE = re.compile("|".join(re.escape(emoji) for emoji in emoji_map.keys()))
CLEAN_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U00002702-\U000027B0"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2640-\u2642"
    "\u2600-\u2B55"
    "]",
    flags=re.UNICODE,
)
ARTEMIS_RE = re.compile(r"\bar(i)?temis\b", flags=re.IGNORECASE)


class Chat(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot
        self.memory: dict[int, list[dict]] = {}
        self.model = "google/gemma-2-2b-it"
        self.client = AsyncInferenceClient(api_key=self.bot.secrets.huggingface)

    def replace_emojis(self, text: str) -> str:
        return EMOJI_RE.sub(lambda match: emoji_map[match.group(0)], text)

    def strip_emojis(self, text: str) -> str:
        return CLEAN_EMOJI_RE.sub("", text)

    def humanize_mentions(self, message: discord.Message, content: str) -> str:
        for user in message.mentions:
            content = content.replace(user.mention, "@" + user.display_name)
        return content

    def get_memory(self, user_id: int):
        if user_id not in self.memory:
            self.memory[user_id] = []
        return self.memory[user_id]

    def add_memory(self, user_id: int, role: str, message: str):
        memory = self.get_memory(user_id)
        if len(memory) == 0:
            message = f"You're Artemis, a friendly AI hanging out in this Discord server, following is a user chat message directed at you.\n\n{message}"
        if len(memory) >= 10:
            del memory[1]
        memory.append({"role": role, "content": message})
        self.memory[user_id] = memory

    def add_user_memory(self, user_id: int, message: str):
        self.add_memory(user_id, "user", message)

    def add_assistant_memory(self, user_id: int, message: str):
        self.add_memory(user_id, "assistant", message)

    async def chat(self, user_id: int, message: str):
        self.add_user_memory(user_id, message)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self.get_memory(user_id),
            max_tokens=500,
            stream=False,
        )
        chat_response = response.choices[0].message.content
        self.add_assistant_memory(user_id, chat_response)
        return chat_response

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        reference = message.reference
        parent = reference.cached_message if reference else None

        is_valid_reply = (
            parent is not None
            and parent.author.id == self.bot.user.id
            and not parent.content.startswith(config.prefix)
        )
        is_valid_mention = (
            message.mentions and self.bot.user in message.mentions
        ) or ARTEMIS_RE.search(message.content)

        if not is_valid_reply and not is_valid_mention:
            return

        content = message.content.replace(self.bot.user.mention, "").strip()
        content = self.humanize_mentions(message, content)

        if not content:
            return

        content = message.author.display_name + ": " + content

        try:
            async with message.channel.typing():
                response = await self.chat(message.author.id, content)
                response = self.replace_emojis(response)
                response = self.strip_emojis(response)
                response = re.sub(r"[ ]{2,}", " ", response)
            await message.reply(response)
        except aiohttp.client_exceptions.ClientResponseError as err:
            await message.reply(f"{self.model} error: {err.status} {err.message}")


async def setup(bot: Artemis):
    await bot.add_cog(Chat(bot))
