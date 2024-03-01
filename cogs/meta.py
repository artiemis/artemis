from __future__ import annotations

import asyncio
import json
import time
from io import StringIO
from typing import TYPE_CHECKING
from urllib.parse import quote

import aiohttp
import discord
import magic
import pendulum
from discord.ext import commands
from discord.utils import format_dt, snowflake_time
from humanize import naturalsize

import utils
from utils.common import ArtemisError
from utils.views import BaseView

if TYPE_CHECKING:
    from bot import Artemis


class Meta(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    @commands.hybrid_command()
    async def ping(self, ctx: commands.Context):
        """Check Websocket latency."""
        curr_ws_lat = round(self.bot.latency * 1000, 1)
        await ctx.reply(f":ping_pong: Pong!\nCurrent WS latency: `{curr_ws_lat}` ms.")

    @commands.command()
    async def uptime(self, ctx: commands.Context):
        """Check the running time of this bot."""
        uptime = round(time.perf_counter() - self.bot.start_time)
        uptime = pendulum.duration(seconds=uptime).in_words(separator=", ")
        embed = discord.Embed(title="I'm up and running!", color=discord.Colour.green())
        embed.set_author(name="Artemis", icon_url=self.bot.user.display_avatar.url)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.set_footer(text="Thanks for checking in on me!")
        await ctx.reply(embed=embed)

    @commands.command()
    async def isdown(self, ctx: commands.Context, url: utils.URL):
        """Check if a site is down."""

        headers = {"User-Agent": self.bot.user_agent}

        await ctx.typing()

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.bot.session.get(url, headers=headers, timeout=timeout) as r:
                buff = await r.content.read(2048)
                if buff:
                    content_type = magic.from_buffer(buff)
                else:
                    content_type = r.content_type

                if r.ok:
                    size = r.headers.get("Content-Length")
                    size = f" • {naturalsize(size, binary=True)}" if size else ""

                    await ctx.reply(
                        f"It's just you! The site is up.\n`HTTP Response: {r.status} {r.reason} • {content_type}{size}`"
                    )
                elif r.status == 404:
                    await ctx.reply(
                        f"It's not just you! Either the resource is down or you entered the wrong URI path.\n`HTTP Response: {r.status} {r.reason} • {content_type}`"
                    )
                else:
                    await ctx.reply(
                        f"It's not just you! The site is down.\n`HTTP Response: {r.status} {r.reason}`"
                    )
        except asyncio.exceptions.TimeoutError:
            await ctx.reply(
                "It's not just you! The site is down.\n`Request timed out, no HTTP response.`"
            )
        except aiohttp.ClientConnectionError as e:
            if "Name or service not known" in str(e):
                msg = f"NXDOMAIN: {str(e).split(':')[-3].split()[-1]} does not exist."
            else:
                msg = "Couldn't establish HTTP connection."
            await ctx.reply(f"It's not just you! The site is down.\n`{msg}`")

    @commands.command(aliases=["ip"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def whois(self, ctx: commands.Context, query: str):
        """IP or domain geo lookup."""
        async with self.bot.session.get(f"http://ip-api.com/json/{quote(query)}") as r:
            data = await r.json()
            ret = json.dumps(data, indent=4, ensure_ascii=False)
            await ctx.reply(self.bot.codeblock(ret, "json"))

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def rawmsg(self, ctx: commands.Context, id: int):
        """
        Display raw message data for message ID.
        The command needs to be invoked in the same channel the message was sent in.
        """
        try:
            message = await self.bot.http.get_message(ctx.channel.id, int(id))
            ret = json.dumps(message, indent=2, ensure_ascii=False)
            dfile = discord.File(StringIO(ret), f"{id}.json")
            await ctx.reply(file=dfile)
        except Exception:
            await ctx.reply("Invalid message ID.")

    @commands.command()
    async def snowflake(self, ctx: commands.Context, id: discord.Member | int):
        """Convert Discord's Snowflake ID or a member mention to a datetime."""
        if isinstance(id, discord.Member):
            id = id.id
        dt = snowflake_time(id)
        dtimestamp = format_dt(dt, "f")
        await ctx.send(dtimestamp)

    def to_discord_timestamp(self, datetime: str):
        try:
            if datetime == "now":
                parsed = pendulum.now("UTC")
            else:
                parsed = pendulum.parse(datetime, tz="UTC")
        except Exception:
            raise ArtemisError("Unable to parse the given string.")

        if len(datetime) == 5:
            fmt = "t"
        elif len(datetime) == 8:
            fmt = "T"
        elif len(datetime) == 10:
            fmt = "D"
        else:
            fmt = "f"

        return format_dt(parsed, fmt)

    @commands.group(invoke_without_command=True)
    async def timestamp(self, ctx: commands.Context, *, datetime: str):
        """
        Converts a UTC datetime or time into a localized Discord timestamp.

        Valid format examples:
        `2022-01-01 14:00:03`
        `2022-01-01 22:00`
        `2039-05-01`
        `12:30:35`
        `15:33`
        `now`

        As well as `RFC 3339` or `ISO 8601` formats.
        """

        msg = self.to_discord_timestamp(datetime)
        await ctx.reply(msg)

    @timestamp.command(name="raw")
    async def timestamp_raw(self, ctx: commands.Context, *, datetime: str):
        """
        Same as the main command but sends the raw markdown that you can use yourself.
        """
        msg = f"`{self.to_discord_timestamp(datetime)}`"
        await ctx.reply(msg)

    @commands.command(aliases=["ffmpeg"])
    async def getffmpeg(self, ctx: commands.Context):
        """ffmpeg-dl script information."""
        view = BaseView(ctx)
        view.add_item(
            discord.ui.Button(
                label="Download", url="https://github.com/artiemis/get-ffmpeg/releases/latest"
            )
        )
        await ctx.reply("https://github.com/artiemis/get-ffmpeg", view=view)


async def setup(bot: Artemis):
    await bot.add_cog(Meta(bot))
