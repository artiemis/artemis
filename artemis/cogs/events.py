from __future__ import annotations
import asyncio
import contextlib

import logging
import random
import re
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from ..utils import config
from ..utils.constants import RIP_EMOJIS, TEEHEE_EMOJIS

if TYPE_CHECKING:
    from ..bot import Artemis

log = logging.getLogger("artemis")

TIKTOK_RE = re.compile(
    r"https://vm\.tiktok\.com/(\w+)|https://(?:www\.)?tiktok\.com/(@.+?/video/\d+)"
)


class Events(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    def suppress_embeds(self, message: discord.Message, delay: float | int = 0):
        async def _suppress():
            await asyncio.sleep(delay)
            with contextlib.suppress(Exception):
                await message.edit(suppress=True)

        asyncio.create_task(_suppress())

    async def handle_triggers(self, message: discord.Message, content: str):
        if content == "good bot":
            emoji = random.choice(TEEHEE_EMOJIS)
            await message.channel.send(emoji)
        elif content == "bad bot":
            emoji = random.choice(RIP_EMOJIS)
            await message.channel.send(emoji)

    async def handle_links(self, message: discord.Message, content: str):
        if message.guild and message.guild.id not in (
            config.main_guild_id,
            config.dev_guild_id,
        ):
            return

        tiktok_url = TIKTOK_RE.search(content)
        if tiktok_url:
            vid = tiktok_url.group(1) or tiktok_url.group(2)
            self.suppress_embeds(message, 0.1)
            return await message.reply(f"https://vm.dstn.to/{vid}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.lower()
        if content.startswith(config.prefix) and f"{config.prefix}jsk" not in content:
            log.info(f"[cmd] {message.author.id}: {message.content}")

        await self.handle_triggers(message, content)
        await self.handle_links(message, content)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.id != self.bot.owner_id:
            return
        if before.content == after.content:
            return
        await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        try:
            await thread.join()
        except Exception:
            pass


async def setup(bot: Artemis):
    await bot.add_cog(Events(bot))
