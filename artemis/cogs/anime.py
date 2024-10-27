from __future__ import annotations

import json
import re
import time
from enum import Enum
from io import BytesIO
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote

import discord
import feedparser
import pendulum
from anilist.async_client import Client as Anilist
from bs4 import BeautifulSoup
from discord.ext import commands
from discord.utils import format_dt

from .. import utils
from ..utils.common import ArtemisError
from ..utils.anilist import build_anilist_embed, build_character_embed
from ..utils.views import DropdownView, ViewPages

if TYPE_CHECKING:
    from ..bot import Artemis


watching_query = """query ($userId: Int, $type: MediaType) {
  MediaListCollection(userId: $userId, type: $type, status: CURRENT) {
    lists {
      entries {
        ...mediaListEntry
      }
    }
  }
}
fragment mediaListEntry on MediaList {
  progress
  media {
    id
    episodes
    nextAiringEpisode {
      episode
      airingAt
    }
    coverImage {
      extraLarge
      color
    }
    title {
      userPreferred
      romaji
      english
      native
    }
  }
}
"""


class Theme(Enum):
    Opening = "OP"
    Ending = "ED"


class Anime(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot
        self.anilist: Anilist = Anilist()

    @commands.command()
    async def aniart(self, ctx: commands.Context):
        """Find out what anime artie is currently watching."""
        payload = {"query": watching_query, "variables": {"userId": 5132095, "type": "ANIME"}}

        await ctx.typing()

        async with self.bot.session.post("https://graphql.anilist.co", json=payload) as r:
            data = await r.json()

        if not data.get("data"):
            return await ctx.reply(f"Anilist Error: {r.status} {r.reason}")

        data = data["data"]["MediaListCollection"]["lists"][0]["entries"]

        if not data:
            return await ctx.reply("Artie is currently not watching any anime :(")

        image_url = data[0]["media"]["coverImage"]["extraLarge"]
        color = data[0]["media"]["coverImage"]["color"]
        desc = ""

        for entry in data:
            media = entry["media"]

            title = media["title"]["userPreferred"]
            mid = media["id"]
            progress = entry["progress"]

            episodes = media["episodes"] or "?"
            next_airing_episode = media["nextAiringEpisode"]
            airing_at = None
            if next_airing_episode:
                next_airing_episode = media["nextAiringEpisode"]["episode"]
                airing_at = media["nextAiringEpisode"]["airingAt"]

            is_caught_up = False

            if next_airing_episode:
                is_caught_up = progress == next_airing_episode - 1

            desc += f"**[{title}](https://anilist.co/anime/{mid})**\n"
            desc += f"Progress: **{progress}/{episodes}**"
            if not is_caught_up:
                if next_airing_episode:
                    behind = next_airing_episode - 1 - progress
                    desc += f" *({behind} episode{'s' if behind > 1 else ''} behind)*"
            if next_airing_episode:
                dt = pendulum.from_timestamp(airing_at, "UTC")
                fmt_dt = format_dt(dt, "R")
                desc += f"\nEpisode {next_airing_episode} airing {fmt_dt}"
            desc += "\n\n"

        embed = discord.Embed(
            title="Artie's Anime Watching List", description=desc, color=int(color[1:], 16)
        )
        embed.set_thumbnail(url=image_url)
        await ctx.reply(embed=embed)

    @commands.command()
    async def anime(self, ctx: commands.Context, *, query: str):
        """Search for anime."""
        await ctx.typing()

        results, _ = await self.anilist.search_anime(query, 10)
        if not results:
            return await ctx.reply("No results found.")

        if len(results) > 1:
            view = DropdownView(
                ctx,
                results,
                lambda x: getattr(x.title, "english", x.title.romaji),
                lambda x: getattr(x.title, "native", None),
                "Choose anime...",
            )
            result = await view.prompt()
            if not result:
                return
            await ctx.typing()
        else:
            result = results[0]

        anime = await self.anilist.get_anime(result.id)
        if not anime:
            return await ctx.reply("Anilist Error: Anime ID not found.")

        embed = build_anilist_embed(anime)

        await ctx.reply(embed=embed)

    @commands.command()
    async def manga(self, ctx: commands.Context, *, query: str):
        """Search for manga."""
        await ctx.typing()

        results, _ = await self.anilist.search_manga(query, 10)
        if not results:
            return await ctx.reply("No results found.")

        if len(results) > 1:
            view = DropdownView(
                ctx,
                results,
                lambda x: getattr(x.title, "english", x.title.romaji),
                lambda x: getattr(x.title, "native", None),
                "Choose manga...",
            )
            result = await view.prompt()
            if not result:
                return
            await ctx.typing()
        else:
            result = results[0]

        manga = await self.anilist.get_manga(result.id)
        if not manga:
            return await ctx.reply("Anilist Error: Manga ID not found.")

        embed = build_anilist_embed(manga)

        await ctx.reply(embed=embed)

    @commands.command(aliases=["chara"])
    async def character(self, ctx: commands.Context, *, query: str):
        """Search for anime and manga characters."""
        await ctx.typing()
        results, _ = await self.anilist.search_character(query, 10)
        if not results:
            return await ctx.reply("No results found.")

        if len(results) > 1:
            view = DropdownView(
                ctx,
                results,
                lambda x: x.name.full,
                lambda x: getattr(x.name, "native", None),
                "Choose a character...",
            )
            result = await view.prompt()
            if not result:
                return
            await ctx.typing()
        else:
            result = results[0]

        await ctx.typing()
        character = await self.anilist.get_character(result.id)
        if not character:
            return await ctx.reply("Anilist Error: Character ID not found.")

        embed = build_character_embed(character)

        await ctx.reply(embed=embed)

    @commands.group(invoke_without_command=True, aliases=["trace"])
    @commands.max_concurrency(1)
    async def whatanime(self, ctx: commands.Context, url: Optional[utils.URL]):
        """
        Reverse search for anime with a screenshot.
        The screenshot can be sent as an attachment or a URL.
        """
        if not ctx.message.attachments and not url:
            return await ctx.reply("Please send me a screenshot first!")
        elif ctx.message.attachments:
            url = ctx.message.attachments[0].url

        await ctx.typing()

        headers = {"User-Agent": ctx.bot.user_agent}
        async with self.bot.session.get(
            f"https://api.trace.moe/search?anilistInfo&url={url}", headers=headers
        ) as r:
            if r.status == 402:
                raise ArtemisError("Error: The bot has reached max API search quota for the month.")
            json = await r.json()
            if json.get("error"):
                raise ArtemisError(json["error"])
            result = json["result"][0]
            anilist = result["anilist"]

        episode = result.get("episode", "N/A")
        episode = episode if episode != "" else "N/A"

        timestamp = result["from"]
        if timestamp >= 3600:  # check if time exceeds one hour
            seconds_format = "%H:%M:%S"
        else:
            seconds_format = "%M:%S"

        timestamp = time.strftime(seconds_format, time.gmtime(timestamp))
        similarity = int(round(result["similarity"], 2) * 100)
        filename = result["filename"]
        anilist_id = anilist["id"]
        titles = anilist["title"]
        is_adult = anilist["isAdult"]
        main_title = titles.get("romaji") or titles.get("english")
        native_title = titles.get("native")
        video = result["video"]
        image = result["image"]

        embed = discord.Embed(
            title=main_title,
            url=f"https://anilist.co/anime/{anilist_id}",
            description=native_title,
            color=self.bot.pink,
        )

        if is_adult and ctx.guild and not ctx.channel.is_nsfw():
            embed.title = main_title + " (NSFW)"
        else:
            embed.set_image(url=image)

        embed.add_field(name="Episode", value=episode, inline=True)
        embed.add_field(name="Timestamp", value=timestamp, inline=True)
        embed.add_field(name="Similarity", value=f"{similarity}%", inline=True)
        embed.add_field(name="Video match", value=f"[{filename}]({video})", inline=False)
        embed.set_footer(text="Powered by trace.moe")
        await ctx.reply(embed=embed)

    @whatanime.command(aliases=["usage"])
    async def quota(self, ctx: commands.Context):
        """
        Returns the search quota left for the month.
        """
        await ctx.typing()
        async with self.bot.session.get("https://api.trace.moe/me") as r:
            data = await r.json()
        quota_left = data["quota"] - data["quotaUsed"]
        first_of_next_month = (
            pendulum.now("UTC").add(months=1).replace(day=1, hour=0, minute=0, second=0)
        )
        await ctx.reply(
            f'API search quota left for the month: **{quota_left}**\nQuota resets {format_dt(first_of_next_month, "R")}.'
        )

    @commands.command(aliases=["sb", "db", "safebooru", "booru"])
    async def danbooru(self, ctx: commands.Context, *, tags: str = None):
        """
        Search for art on Danbooru or show a random image.
        This uses the common tag search logic found on booru imageboards, fuzzy matching for tags is enabled.
        """
        params = None

        await ctx.typing()

        include_nsfw = not ctx.guild or ctx.channel.nsfw
        if not tags:
            if include_nsfw:
                params = {}
            else:
                params = {"post[tags]": "rating:g"}
        elif tags:
            valid_tags = len([tag for tag in tags.split(" ") if not tag.startswith("rating")])
            if valid_tags > 1:
                return await ctx.reply(
                    "You cannot search for more than 2 tags at a time (rating:g already included in SFW channels)."
                )

            if include_nsfw:
                params = {"post[tags]": tags}
            else:
                params = {"post[tags]": f"rating:g {tags}"}

        params["limit"] = "25"
        params["random"] = "true"

        async with self.bot.session.get(
            "https://danbooru.donmai.us/posts.json", params=params
        ) as r:
            posts = await r.json()

        posts = [post for post in posts if post.get("id") and post.get("large_file_url")]
        if not posts:
            return await ctx.reply("No posts matching the tags found.")

        embeds = []
        for post in posts:
            pid = post["id"]
            character = post.get("tag_string_character")
            artist = post.get("tag_string_artist")
            tags = post["tag_string"].strip().split(" ")
            tags = ", ".join(tags[:3])

            title = (character or tags).replace("_", "\\_")
            url = f"https://danbooru.donmai.us/posts/{pid}"
            img_url = post["large_file_url"]

            embed = discord.Embed(title=utils.trim(title, 256), url=url, color=0x0075F8)
            embed.set_image(url=img_url)
            embed.set_footer(text="Powered by Danbooru API")
            embed.set_author(name=artist or "Danbooru")
            embeds.append(embed)

        view = ViewPages(ctx, embeds)
        await view.start()

    @commands.command(
        help="Search for torrents on Nyaa.\nSorted by seeds, if no query is given, shows recently uploaded torrents."
    )
    async def nyaa(self, ctx: commands.Context, *, query: Optional[str] = None):
        """
        Search for torrents on Nyaa.
        Sorted by seeds, if no query is given, shows recently uploaded torrents.
        """
        if not query:
            params = None
        else:
            params = {"q": query}

        await ctx.typing()
        async with self.bot.session.get("https://nyaa.si/?page=rss", params=params) as r:
            parsed = feedparser.parse(await r.text())

        if not parsed.entries:
            return await ctx.reply("No torrents found.")

        entries = parsed.entries
        if query:
            entries = sorted(entries, key=lambda x: int(x.get("nyaa_seeders")), reverse=True)

        data = []
        for torrent in entries[:50]:
            title = torrent.title
            guid = torrent.id
            link = torrent.link
            size = torrent.get("nyaa_size", "N/A")
            category = torrent.get("nyaa_category", "N/A")
            seeders = torrent.get("nyaa_seeders", "N/A")
            leechers = torrent.get("nyaa_leechers", "N/A")
            data.append(
                f"**[{title}]({guid})**\n**{size}** | {category} | **{seeders}** :green_heart: • **{leechers}** :yellow_heart: | [.torrent]({link})\n"
            )

        embed = discord.Embed(title="Results", colour=discord.Color.blue())
        embed.set_author(name="Nyaa", icon_url="https://nyaa.si/static/favicon.png")
        embeds = utils.make_embeds(data, embed)

        view = ViewPages(ctx, embeds)
        await view.start()

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def pixiv(self, ctx: commands.Context, url: utils.URL):
        """Returns the original-res pixiv image for a given art URL for easy sharing/embedding."""
        PIXIV_RE = r"https:\/\/(?:www\.)?pixiv\.net(?:\/\w+)?\/artworks\/(?P<pid>\d+)\/?"

        async with ctx.typing():
            match = re.fullmatch(PIXIV_RE, url)
            if not match:
                return await ctx.reply("Invalid pixiv URL.")

            pid = match.group("pid")
            headers = {"User-Agent": self.bot.user_agent, "Referer": "https://www.pixiv.net/"}
            async with self.bot.session.get(url, headers=headers) as r:
                if r.status != 200:
                    return await ctx.reply(f"Pixiv Error: {r.status} {r.reason}")
                html = await r.text()

            soup = BeautifulSoup(html, "lxml")
            try:
                meta = soup.select_one("#meta-preload-data")
                if not meta:
                    return await ctx.reply("Pixiv Error: No preload data found.")

                data = meta["content"]

                data = json.loads(data)
                original_url = data["illust"][pid]["urls"]["original"]
            except Exception:
                return await ctx.reply("Pixiv Error: No image data found.")

            async with self.bot.session.get(original_url, headers=headers) as r:
                if r.status != 200:
                    return await ctx.reply(f"Pixiv Error: {r.status} {r.reason}")
                img = await r.read()
                img_size = len(img)
                img = BytesIO(img)

            try:
                adult = any([tag["tag"] == "R-18" for tag in data["illust"][pid]["tags"]["tags"]])
            except Exception:
                adult = False

            ext = original_url.split("/")[-1].split(".")[-1].split("?")[0]
            filename = f"{pid}.{ext}"
            if adult:
                filename = f"SPOILER_{filename}"

            if img_size <= utils.MAX_DISCORD_SIZE:
                dfile = discord.File(img, filename)
                return await ctx.reply(file=dfile)
            else:
                img.name = filename
                try:
                    res = await self.bot.litterbox.upload(img, 24)
                    return await ctx.reply(res)
                except Exception as err:
                    return await ctx.reply(f"Upload Error: {err}")

    async def search_themes(self, ctx: commands.Context, query: str, theme_type: Theme):
        data = await self.bot.cache.get(f"anithemes:{query}")
        if not data:
            request_url = f"https://api.animethemes.moe/search?fields[search]=anime&include[anime]=animethemes.animethemeentries.videos&limit=10&q={quote(query)}"
            headers = {"User-Agent": self.bot.user_agent}

            await ctx.typing()

            async with self.bot.session.get(request_url, headers=headers) as r:
                data = await r.json()
                await self.bot.cache.set(f"anithemes:{query}", data, ttl=60 * 60)

        results = data["search"]["anime"]
        if not results:
            return await ctx.reply("No results found.")
        elif len(results) == 1:
            anime = results[0]
        else:
            view = DropdownView(
                ctx,
                results,
                lambda x: x["name"],
                lambda x: x["slug"],
                placeholder="Choose anime...",
            )
            anime = await view.prompt()
            if not anime:
                return

        anime_slug = anime["slug"]

        themes = anime["animethemes"]
        themes = [theme for theme in themes if theme["type"] == theme_type.value]
        if not themes:
            return await ctx.reply(f"No {theme_type.value} for this anime found.")

        items = []
        for theme in themes:
            for entry in theme["animethemeentries"]:
                try:
                    video = entry["videos"][0]
                    version = entry.get("version")
                    tags = video.get("tags")

                    slug = theme["slug"]
                    if version and version != 1:
                        slug += version
                    if tags:
                        slug += f"-{tags}"

                    link = f"https://animethemes.moe/anime/{anime_slug}/{slug}"
                except Exception:
                    continue
                msg = f"**{anime['name']} {theme['type']}{theme['sequence'] or 1}**\n"

                episodes = entry["episodes"]
                if episodes:
                    msg += f"`episodes: {episodes}`\n"

                msg += f"{link}"
                items.append(msg)

        view = ViewPages(ctx, items)
        await view.start()

    @commands.command(aliases=["op"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def opening(self, ctx: commands.Context, *, query: str):
        """Search for anime openings."""
        await self.search_themes(ctx, query, Theme.Opening)

    @commands.command(aliases=["ed"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def ending(self, ctx: commands.Context, *, query: str):
        """Search for anime endings."""
        await self.search_themes(ctx, query, Theme.Ending)


async def setup(bot: Artemis):
    await bot.add_cog(Anime(bot))
