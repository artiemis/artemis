from __future__ import annotations

import asyncio
import logging
from pathlib import Path
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
        self.memory: list[dict] = []
        self.model = "google/gemma-2-2b-it"
        self.prompt = self.read_prompt()
        self.client = AsyncInferenceClient(api_key=self.bot.secrets.huggingface)
        self.lock = asyncio.Lock()

    def read_prompt(self):
        return Path("temp/prompt").read_text() if Path("temp/prompt").exists() else ""

    def write_prompt(self, prompt: str):
        Path("temp/prompt").write_text(prompt)

    def replace_emojis(self, text: str) -> str:
        return EMOJI_RE.sub(lambda match: emoji_map[match.group(0)], text)

    def strip_emojis(self, text: str) -> str:
        return CLEAN_EMOJI_RE.sub("", text)

    def humanize_mentions(self, message: discord.Message, content: str) -> str:
        for user in message.mentions:
            content = content.replace(user.mention, "@" + user.display_name)
        return content

    def add_memory(self, role: str, message: str):
        prompt = (
            self.prompt
            + "The following is a user chat message directed at you, the format will be the same for subsequent messages, respond with only the message content, without specyfing actions."
            + "\n\n"
        )
        if len(self.memory) == 0:
            message = prompt + message
        if len(self.memory) >= 15:
            del self.memory[0]
            del self.memory[0]
            self.memory[0] = {"role": "user", "content": prompt + self.memory[0]["content"]}
        self.memory.append({"role": role, "content": message})

    def add_user_memory(self, message: str):
        self.add_memory("user", message)

    def add_assistant_memory(self, message: str):
        self.add_memory("assistant", message)

    async def chat(self, message: str):
        self.add_user_memory(message)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self.memory,
            max_tokens=500,
            stream=False,
        )
        chat_response = response.choices[0].message.content

        chat_response = self.replace_emojis(chat_response)
        chat_response = self.strip_emojis(chat_response)
        chat_response = re.sub(r"[ ]{2,}", " ", chat_response)
        chat_response = re.sub(r"[\n]{2,}", "\n", chat_response)

        self.add_assistant_memory(chat_response)
        return chat_response

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.content.startswith(config.prefix):
            return

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

        content = f"[USERNAME]: {message.author.display_name}\n[MESSAGE]: {content}"

        try:
            async with message.channel.typing():
                async with self.lock:
                    response = await self.chat(content)
            await message.reply(response)
        except aiohttp.client_exceptions.ClientResponseError as err:
            await message.reply(f"{self.model} error: {err.status} {err.message}")

    @commands.group(name="chat")
    async def _chat(self, ctx: commands.Context):
        """LLM chat management."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid subcommand passed.")

    @_chat.command()
    async def reset(self, ctx: commands.Context):
        """Reset chat memory."""
        self.memory = []
        await ctx.send("Chat memory reset.")

    @_chat.command(name="prompt")
    async def _prompt(self, ctx: commands.Context, *, prompt: str = None):
        """Get or set system prompt and reset chat memory."""
        if not prompt:
            await ctx.send(self.prompt)
            return
        self.prompt = prompt
        self.write_prompt(prompt)
        self.memory = []
        await ctx.send("Prompt updated.")


async def setup(bot: Artemis):
    await bot.add_cog(Chat(bot))
