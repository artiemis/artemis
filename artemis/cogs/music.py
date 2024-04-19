from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from .. import utils
from ..utils.views import DropdownView
from .media import DEFAULT_OPTS, run_ytdlp

if TYPE_CHECKING:
    from ..bot import Artemis


async def in_voice_channel(ctx: commands.Context):
    client = ctx.voice_client
    voice = ctx.author.voice
    if client and voice and voice.channel and client.channel and voice.channel == client.channel:
        return True
    elif not client:
        raise commands.CheckFailure("I am not connected to a voice channel.")
    else:
        raise commands.CheckFailure("You need to be in my voice channel to do that.")


async def audio_playing(ctx: commands.Context):
    client = ctx.voice_client
    if client and client.channel and client.is_playing():
        return True
    else:
        raise commands.CheckFailure("Not playing any audio.")


@dataclass
class SongInfo:
    title: str
    url: str
    webpage_url: Optional[str]
    embed: discord.Embed
    requestor: int
    ctx: commands.Context


@dataclass
class MusicState:
    song: Optional[SongInfo]
    connected: bool

    @property
    def requestor(self):
        if not self.song:
            return None
        return self.song.requestor


class Music(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot
        self.ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
        self.state = MusicState(None, False)
        self.queue: deque[SongInfo] = deque([], 10)

    def cleanup(self):
        self.state.connected = False
        self.state.song = None
        self.queue.clear()

    async def cog_check(self, ctx: commands.Context):
        if ctx.guild.id not in (338684864008290304, 789168201295724574):
            raise commands.CheckFailure("Music features are not supported in this server.")
        return True

    def is_requestor(self, ctx: commands.Context[Artemis]):
        client = ctx.voice_client
        requestor = self.state.requestor
        if ctx.author.id == ctx.bot.owner_id or not requestor:
            return True
        return bool(client and client.is_playing() and ctx.author.id == requestor)

    def build_embed(self, ctx: commands.Context, info_dict: dict) -> discord.Embed:
        title = info_dict["title"]
        url = info_dict.get("webpage_url") or None
        uploader = info_dict.get("uploader") or ""
        thumbnail = info_dict.get("thumbnail")
        colour = 0xFF0000 if info_dict["extractor"] == "youtube" else self.bot.pink
        embed = discord.Embed(title=title, url=url, colour=colour)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_author(name=uploader)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return embed

    async def search_youtube(self, query: str) -> list[dict]:
        headers = {"User-Agent": self.bot.user_agent}
        params = {"search_query": query}

        async with self.bot.session.get(
            "https://youtube.com/results", headers=headers, params=params
        ) as r:
            html = await r.text()

        data = re.search(r"var\s?ytInitialData\s?=\s?(\{.*?\});", html).group(1)
        data = json.loads(data)
        videos = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"][
            "sectionListRenderer"
        ]["contents"][0]["itemSectionRenderer"]["contents"]

        results = []
        for video in videos:
            if "videoRenderer" in video:
                video_data = video["videoRenderer"]
                results.append(
                    {
                        "title": video_data.get("title", {})
                        .get("runs", [[{}]])[0]
                        .get("text", None),
                        "id": video_data.get("videoId", None),
                        "uploader": video_data.get("longBylineText", {})
                        .get("runs", [[{}]])[0]
                        .get("text", None),
                    }
                )
        return results

    async def resolve_query(self, ctx: commands.Context, query: str):
        url_or_query = query.strip("<>")
        if not utils.is_valid_url(url_or_query):  # Try scraping YT search
            try:
                results = await self.search_youtube(url_or_query)
                if results:
                    view = DropdownView(
                        ctx,
                        results,
                        lambda x: x["title"],
                        lambda x: x["uploader"],
                        "Choose a video...",
                    )
                    result = await view.prompt()
                    if not result:
                        return
                    url_or_query = f"https://www.youtube.com/watch?v={result['id']}"
                    await ctx.typing()
            except Exception:
                pass
        else:
            utils.check_for_ssrf(url_or_query)

        ytdl_opts = {**DEFAULT_OPTS, "default_search": "auto", "format": "251/ba*"}
        info_dict = await run_ytdlp(url_or_query, ytdl_opts, download=False)
        if info_dict.get("entries"):
            info_dict = info_dict["entries"][0]

        url = info_dict["url"]
        webpage_url = info_dict.get("webpage_url")
        title = info_dict.get("title") or info_dict.get("id")
        embed = self.build_embed(ctx, info_dict)
        return SongInfo(title, url, webpage_url, embed, ctx.author.id, ctx)

    async def real_play(self):
        def my_after(error):
            coro = self.real_play()
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            fut.result()

        try:
            self.state.song = next_song = self.queue.popleft()
        except IndexError:
            self.state.song = None
            return

        source = await discord.FFmpegOpusAudio.from_probe(next_song.url, **self.ffmpeg_options)
        next_song.ctx.voice_client.play(source, after=my_after)
        await next_song.ctx.send(":musical_note:  Now playing:", embed=next_song.embed)

    @commands.command()
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice:
            return await ctx.reply("You are not connected to a voice channel.")

        if ctx.voice_client:
            await ctx.voice_client.move_to(ctx.author.voice.channel)
        else:
            if self.state.connected:
                return await ctx.reply("Sorry, but I can only play in one server at a time.")
            await ctx.author.voice.channel.connect(reconnect=True)
        self.state.connected = True

    @commands.command()
    @commands.check(in_voice_channel)
    async def play(self, ctx: commands.Context, *, url_or_query: str):
        await ctx.typing()

        if ctx.voice_client.is_playing():
            if len(self.queue) == 10:
                return await ctx.reply("The queue is full!")
            song = await self.resolve_query(ctx, url_or_query)
            if not song:
                return
            self.queue.append(song)
            return await ctx.reply(":ballot_box_with_check:  Added to queue.", embed=song.embed)

        song = await self.resolve_query(ctx, url_or_query)
        self.queue.append(song)
        await self.real_play()

    @commands.command()
    @commands.check(in_voice_channel)
    @commands.check(audio_playing)
    async def queue(self, ctx: commands.Context):
        if not self.queue:
            return await ctx.reply("The queue is empty.")

        desc = ""
        for idx, song in enumerate(self.queue, start=1):
            desc += f"`{idx}.` [{song.title}]({song.webpage_url})\n"

        embed = discord.Embed(title="🎵  Song Queue", description=desc, color=self.bot.invisible)
        await ctx.reply(embed=embed)

    @commands.command(name="clearqueue")
    @commands.check(in_voice_channel)
    @commands.check(audio_playing)
    @commands.is_owner()
    async def clear_queue(self, ctx: commands.Context):
        if not self.queue:
            return await ctx.reply("The queue is already empty.")
        else:
            self.queue.clear()
            return await ctx.reply("The queue has been cleared.")

    @commands.command()
    @commands.check(in_voice_channel)
    @commands.check(audio_playing)
    async def skip(self, ctx: commands.Context):
        if self.is_requestor(ctx):
            ctx.voice_client.stop()
        else:
            return await ctx.reply("You cannot skip a song you did not request.")

    @commands.command(aliases=["dc"])
    @commands.check(in_voice_channel)
    async def disconnect(self, ctx: commands.Context):
        if self.queue:
            return await ctx.reply("Cannot disconnect with a filled queue.")
        if self.is_requestor(ctx):
            await ctx.voice_client.disconnect()
            self.cleanup()
        else:
            return await ctx.reply(
                "You cannot disconnect me while playing a song you did not request."
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after
    ):
        voice = member.guild.voice_client
        if not voice:
            return
        if len(voice.channel.members) < 2:
            await voice.disconnect()
            self.cleanup()


async def setup(bot: Artemis):
    await bot.add_cog(Music(bot))
