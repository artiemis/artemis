from __future__ import annotations

import http
import random
import re
from typing import TYPE_CHECKING, Optional, TypedDict
from urllib.parse import quote

import discord
import pendulum
from bs4 import BeautifulSoup
from discord.ext import commands

from .. import utils
from ..utils import config
from ..utils.common import ArtemisError, read_json, trim
from ..utils.views import ViewPages

if TYPE_CHECKING:
    from ..bot import Artemis


class Pokemon(TypedDict):
    abilities: list[str]
    detailPageURL: str
    weight: float
    weakness: list[str]
    number: str
    height: int
    slug: str
    name: str
    ThumbnailImage: str
    id: int
    type: list[str]


Pokedex = list[Pokemon]

pokedex = read_json("data/pokedex.json")
fim_transcripts = read_json("data/fim-dialogues.json")


class Funhouse(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    def fun_embed(self, description: str) -> discord.Embed:
        return discord.Embed(
            description=description, timestamp=pendulum.now("UTC"), colour=discord.Colour.random()
        )

    async def invoke_reddit(self, ctx: commands.Context, subreddit: str):
        reddit = self.bot.get_command("reddit")
        return await reddit(ctx, subreddit)

    @commands.command()
    async def hug(self, ctx: commands.Context, member: discord.Member):
        """Hug someone."""
        async with self.bot.session.get("https://some-random-api.ml/animu/hug") as r:
            json = await r.json()
            url = json["link"]
            embed = self.fun_embed(f"{ctx.author.mention} hugged {member.mention}!")
            embed.set_image(url=url)
            await ctx.send(embed=embed)

    @commands.command()
    async def pat(self, ctx: commands.Context, member: discord.Member):
        """Pat someone."""
        async with self.bot.session.get("https://some-random-api.ml/animu/pat") as r:
            json = await r.json()
            url = json["link"]
            embed = self.fun_embed(f"{ctx.author.mention} pats {member.mention}!")
            embed.set_image(url=url)
            await ctx.send(embed=embed)

    @commands.command()
    async def bonk(self, ctx: commands.Context, member: discord.Member):
        """Bonk someone."""
        async with self.bot.session.get("https://waifu.pics/api/sfw/bonk") as r:
            json = await r.json()
            url = json["url"]
            embed = self.fun_embed(f"{ctx.author.mention} bonked {member.mention}!")
            embed.set_image(url=url)
            await ctx.send(embed=embed)

    @commands.command()
    async def httpcat(self, ctx: commands.Context, code: int):
        """Sends a cat for the given HTTP code."""
        try:
            code = http.HTTPStatus(code).value
            await ctx.reply(f"https://http.cat/{code}")
        except Exception:
            await ctx.reply("https://http.cat/404")

    @commands.command()
    async def httpdog(self, ctx: commands.Context, code: int):
        """Sends a dog for the given HTTP code."""
        try:
            code = http.HTTPStatus(code).value
            await ctx.reply(f"https://http.dog/{code}.jpg")
        except Exception:
            await ctx.reply("https://http.dog/404.jpg")

    @commands.command(aliases=["av"])
    async def avatar(self, ctx: commands.Context, user: Optional[discord.User]):
        """
        Returns your or another user's avatar.
        Works with names, mentions and IDs.
        """
        if not user:
            user = ctx.message.author
        if user.display_avatar.is_animated():
            url = gif = user.display_avatar.replace(size=4096, format="gif").url
            static = user.display_avatar.replace(size=4096, format="png").url
            description = f"[gif]({gif}) | [static]({static})"
        else:
            url = png = user.display_avatar.replace(size=4096, format="png").url
            jpg = user.display_avatar.replace(size=4096, format="jpg").url
            webp = user.display_avatar.replace(size=4096, format="webp").url
            description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"

        embed = discord.Embed(
            description=description,
            color=user.colour if user.colour.value != 0 else self.bot.invisible,
        )
        embed.set_image(url=url)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command()
    async def banner(self, ctx: commands.Context, user: discord.User = None):
        """
        Returns your or another user's custom banner.
        Works with names, mentions and IDs.
        """
        if not user:
            user = ctx.author

        if user.id in [member.id for member in self.bot.users]:
            user = await self.bot.fetch_user(user.id)

        banner: discord.Asset = user.banner
        if not banner:
            banner_colour = user.accent_colour
            if banner_colour:
                colour_cmd = self.bot.get_command("color")
                return await colour_cmd(ctx, colour=banner_colour)
            else:
                raise ArtemisError(f"{user.display_name} does not have a custom banner set.")

        if banner.is_animated():
            url = gif = banner.replace(size=4096, format="gif").url
            static = banner.replace(size=4096, format="png").url
            description = f"[gif]({gif}) | [static]({static})"
        else:
            url = png = banner.replace(size=4096, format="png").url
            jpg = banner.replace(size=4096, format="jpg").url
            webp = banner.replace(size=4096, format="webp").url
            description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"

        embed = discord.Embed(description=description, color=self.bot.invisible)
        embed.set_image(url=url)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.group(name="reddit", invoke_without_command=True)
    async def reddit_(self, ctx: commands.Context, subreddit: str = "all"):
        """Shows a random post from reddit or a given subreddit."""

        async with ctx.typing():
            post = await self.bot.reddit.random(subreddit)
            embeds = await post.to_embed(ctx.message)

        await ctx.reply(embeds=embeds)

    @reddit_.command()
    async def show(self, ctx: commands.Context, pid: str):
        """Displays a rich reddit post embed for a given post ID."""
        await ctx.typing()

        post = await self.bot.reddit.post(pid=pid)
        if not post:
            raise ArtemisError("Invalid post ID.")

        embeds = await post.to_embed(ctx.message)
        await ctx.reply(embeds=embeds)

    @commands.command(aliases=["4chan", "da"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def desuarchive(self, ctx: commands.Context, board: str, *, query: str):
        """
        Search through the desuarchive.
        <board> - board actively archived by desuarchive or "all"
        """
        icon = "https://desuarchive.org/favicon.ico"
        headers = {"User-Agent": self.bot.user_agent}
        banned_boards = ["aco", "d", "gif"]

        board = quote(board)
        query = quote(query)

        if board == "all":
            board = "_"
        elif board in banned_boards:
            return await ctx.reply("Only SFW boards are allowed.")

        await ctx.typing()

        async with self.bot.session.get(
            f"https://desuarchive.org/{board}/search/text/{query}", headers=headers
        ) as r:
            html = await r.text()
            if "Page not found." in html:
                return await ctx.reply("Board not found.")
            elif "No results found." in html:
                return await ctx.reply("No results found.")
            soup = BeautifulSoup(html, "lxml")

        embeds = []
        posts = soup.select(".post_wrapper")
        for post in posts:
            title = post.select_one(".post_title").text
            if not title:
                title = f"{post.select_one('.post_author').text} {post.select_one('time').text} UTC"

            post_url = post.find(
                "a", attrs={"href": re.compile(r"https://desuarchive.org/.*?/thread/")}
            )["href"]
            board = post_url.split("/")[-4]
            if board in banned_boards:
                continue
            board_url = f"https://desuarchive.org/{board}/"

            description = post.select_one(".text")
            for br in description.select("br"):
                br.replace_with("\n")
            description = trim(re.sub(r"(>)(\w.*)", r"\g<1> \g<2>", description.text), 4096)

            img = post.select_one(".thread_image_box .thread_image_link")

            embed = discord.Embed(
                title=title, description=description, url=post_url, color=self.bot.invisible
            )
            embed.set_author(name=f"desuarchive - /{board}/", url=board_url, icon_url=icon)
            if img:
                embed.set_image(url=img["href"])
            embeds.append(embed)

        view = ViewPages(ctx, embeds)
        await view.start()

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def codewaifu(self, ctx: commands.Context, *, lang: str = None):
        """[Anime girls holding programming books.](https://github.com/cat-milk/Anime-Girls-Holding-Programming-Books)"""
        repo = "https://api.github.com/repos/cat-milk/Anime-Girls-Holding-Programming-Books"
        alt = {
            "js": "javascript",
            "assembly": "asm",
            "golang": "go",
            "mongo": "mongodb",
            "ray tracing": "raytracing",
            "quantum": "quantum computing",
            "ts": "typescript",
            "vb": "visual basic",
            "cpp": "c++",
        }

        langs = await self.bot.cache.get("anime_books:langs")
        if not langs:
            await ctx.typing()
            async with self.bot.session.get(f"{repo}/contents") as r:
                data = await r.json()
                langs = [entry["name"] for entry in data if entry["type"] == "dir"]
                await self.bot.cache.set("anime_books:langs", langs)

        if not lang:
            lang = random.choice(langs)
        else:
            if lang in alt:
                lang = alt[lang]

            lang = utils.fuzzy_search_one(lang, langs, cutoff=70)
            if not lang:
                return await ctx.reply("No code waifus for that language found.")
            lang = quote(lang)

        data = await self.bot.cache.get(f"anime_books:{lang}")
        if not data:
            async with self.bot.session.get(f"{repo}/contents/{lang}") as r:
                await ctx.typing()
                data = await r.json()
                await self.bot.cache.set(f"anime_books:{lang}", data, ttl=3600)

        img = random.choice(data)
        await ctx.reply(img["download_url"])

    @commands.command(aliases=["fs"])
    async def foalsay(self, ctx: commands.Context, *, query: str):
        """
        Search for dialogue lines in MLP:FiM transcripts.
        [Command name generated with ChatGPT.](https://files.catbox.moe/e66t2g.png)
        """
        if len(query) < 3:
            return await ctx.reply("Your search term must be at least 3 characters long!")

        query = query.strip().lower()

        results = []
        for entry in fim_transcripts:
            lines = entry["text"].splitlines()

            for idx, line in enumerate(lines):
                line = line.split(":", 1)[-1].strip()
                if not line:
                    continue

                if query in line.lower():
                    results.append({"line": idx, "entry": entry})

        if not results:
            return await ctx.reply("No results found.")

        embeds = []
        for result in results:
            url = result["entry"]["url"]
            url = url[:28] + "Transcripts/" + url[28:]

            embed = discord.Embed(title=result["entry"]["title"], url=url, color=0x883E97)
            embed.set_author(
                name="Pony Transcripts", icon_url="https://files.catbox.moe/h1wxle.png"
            )

            line_no = result["line"]
            lines = result["entry"]["text"].splitlines()
            line = lines[line_no]

            embed.description = ""

            line_before = lines[line_no - 1 : line_no]
            if line_before:
                embed.description += f"{line_before[0]}\n"

            # embed.description += f"**{line}**\n"
            line = re.sub(rf"({query})", r"**\g<1>**", line, flags=re.IGNORECASE)
            embed.description += f"{line}\n"

            line_after = lines[line_no + 1 : line_no + 2]
            if line_after:
                embed.description += f"{line_after[0]}\n"

            embed.description = re.sub(r"(^.+?):", r"**\g<1>**:", embed.description, flags=re.M)

            embeds.append(embed)

        view = ViewPages(ctx, embeds)
        await view.start()

    @commands.command(name="pokedex", aliases=["poke", "pokémon", "pokemon", "poké", "pokédex"])
    async def _pokedex(self, ctx: commands.Context, *, query: str):
        """Search for a pokémon."""
        type_map = {
            "normal": 11053176,
            "fire": 15761456,
            "fighting": 12595240,
            "water": 6852848,
            "flying": 11047152,
            "grass": 7915600,
            "poison": 10502304,
            "electric": 16306224,
            "ground": 14729320,
            "psychic": 16275592,
            "rock": 12099640,
            "ice": 10016984,
            "bug": 11057184,
            "dragon": 7354616,
            "ghost": 7362712,
            "dark": 7362632,
            "steel": 12105936,
            "fairy": 15636908,
            "???": 6856848,
        }

        if query.isdigit():
            result = next((entry for entry in pokedex if entry["id"] == int(query)), None)
        else:
            result = utils.fuzzy_search_one(query, pokedex, "name", cutoff=60)

        if not result:
            raise ArtemisError("Pokémon not found.")

        embed = discord.Embed(
            title=result["name"], url="https://www.pokemon.com/us/pokedex/" + result["slug"]
        )
        embed.color = type_map.get(result["type"][0].lower(), type_map["???"])

        embed.set_author(
            name="#" + result["number"], icon_url="https://www.pokemon.com/favicon.ico"
        )
        embed.set_image(url=f"{config.cdn_base_url}/pokedex/{result['id']:>03}.png")

        types = ", ".join([t.title() for t in result["type"]])
        abilities = ", ".join(result["abilities"])
        weaknesses = ", ".join(result["weakness"])

        embed.add_field(name="Type", value=types, inline=False)
        embed.add_field(name="Abilities", value=abilities, inline=False)
        embed.add_field(name="Weaknesses", value=weaknesses, inline=False)

        await ctx.reply(embed=embed)


async def setup(bot: Artemis):
    await bot.add_cog(Funhouse(bot))
