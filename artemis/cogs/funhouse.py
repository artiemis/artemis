from __future__ import annotations

import http
import mimetypes
import random
import re
from io import BytesIO
from typing import TYPE_CHECKING, Optional, TypedDict
from urllib.parse import quote

import discord
import pendulum
from bs4 import BeautifulSoup
from discord.ext import commands

from .. import utils
from ..utils import config
from ..utils.common import ArtemisError, read_json, trim
from ..utils.views import DropdownView, ViewPages

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
    async def cat(self, ctx: commands.Context):
        """Random cat picture."""
        await ctx.typing()
        async with self.bot.session.get("https://cataas.com/cat") as r:
            ext = mimetypes.guess_extension(r.content_type)
            image = discord.File(BytesIO(await r.read()), f"{utils.time()}.{ext}")
            await ctx.send(file=image)

    @commands.command()
    async def dog(self, ctx: commands.Context):
        """Random dog picture."""
        async with self.bot.session.get("https://random.dog/woof.json") as r:
            json = await r.json(content_type=None)
            await ctx.send(json["url"])

    @commands.command()
    async def fox(self, ctx: commands.Context):
        """Random fox picture."""
        async with self.bot.session.get("https://randomfox.ca/floof/") as r:
            json = await r.json(content_type=None)
            await ctx.send(json["image"])

    @commands.command()
    async def waifu(self, ctx: commands.Context):
        """Random waifu (anime girl)."""
        await self.invoke_reddit(ctx, "awwnime")

    @commands.command()
    async def husbando(self, ctx: commands.Context):
        """Random husbando (anime boy)."""
        sub = random.choice(("cuteanimeboys", "bishounen"))
        await self.invoke_reddit(ctx, sub)

    @commands.command()
    async def yuri(self, ctx: commands.Context):
        """Random yuri (anime lesbian couple) art."""
        await self.invoke_reddit(ctx, "wholesomeyuri")

    @commands.command()
    async def neko(self, ctx: commands.Context):
        """Random neko (anime cat girl/boy)."""
        db = self.bot.get_command("db")
        await db(ctx, tags="cat_ears")

    @commands.command()
    @commands.is_nsfw()
    async def ecchi(self, ctx: commands.Context):
        """
        Random ecchi image.
        NSFW channels only.
        """
        db = self.bot.get_command("db")
        await db(ctx, tags="rating:q score:>10")

    @commands.command()
    @commands.is_nsfw()
    async def hentai(self, ctx: commands.Context):
        """
        Random hentai image.
        NSFW channels only.
        """
        db = self.bot.get_command("db")
        await db(ctx, tags="rating:e score:>10")

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

    @commands.group(aliases=["ffxiv"])
    async def xiv(self, ctx: commands.Context):
        """Final Fantasy XIV commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid subcommand passed.")

    @xiv.command(aliases=["chara"])
    async def character(self, ctx: commands.Context, *, query: str):
        """Search for player characters in all worlds."""
        LODESTONE_URL = "https://eu.finalfantasyxiv.com/lodestone/character/"

        await ctx.typing()

        params = {"name": query, "columns": "ID,Name,Server"}
        async with self.bot.session.get("https://xivapi.com/character/search", params=params) as r:
            if not r.ok:
                return await ctx.reply(f"XIV API Error: {r.status} {r.reason}")
            data = await r.json()

        characters = data["Results"]
        if not characters:
            return await ctx.reply("No results found.")
        elif len(characters) == 1:
            character = characters[0]
        else:
            view = DropdownView(ctx, characters, lambda x: x["Name"], lambda x: x["Server"])
            character = await view.prompt("Which character?")
            if not character:
                return
            await ctx.typing()

        chid = character["ID"]
        params = {
            "columns": "Character.Name,Character.Avatar,Character.Portrait,Character.ActiveClassJob"
        }
        async with self.bot.session.get(f"https://xivapi.com/character/{chid}", params=params) as r:
            if not r.ok:
                return await ctx.reply(f"XIV API Error: {r.status} {r.reason}")
            data = await r.json()

        character = data["Character"]

        name = character["Name"]
        url = LODESTONE_URL + str(chid)
        portrait_url = character["Portrait"]
        avatar_url = character["Avatar"]

        embed = discord.Embed(title=name, url=url, color=0x293C66)
        embed.set_image(url=portrait_url)
        embed.set_thumbnail(url=avatar_url)
        embed.set_author(
            name="The Lodestone",
            icon_url="https://img.finalfantasyxiv.com/lds/h/0/U2uGfVX4GdZgU1jASO0m9h_xLg.png",
        )

        active_job = character["ActiveClassJob"]
        job_name = active_job["Name"].title()
        job_level = active_job["Level"]
        embed.description = f"Level **{job_level}**\n{job_name}"

        await ctx.reply(embed=embed)

    @xiv.command()
    async def item(self, ctx: commands.Context, *, query: str):
        """Search for items."""
        await ctx.typing()

        params = {"string": query, "columns": "Name,Url", "indexes": "item"}
        async with self.bot.session.get("https://xivapi.com/search", params=params) as r:
            if not r.ok:
                return await ctx.reply(f"XIV API Error: {r.status} {r.reason}")
            data = await r.json()

        results = data["Results"]
        if not results:
            return await ctx.reply("No results found.")
        elif len(results) == 1:
            result = results[0]
        else:
            view = DropdownView(ctx, results, lambda x: x["Name"])
            result = await view.prompt("Which item?")
            if not result:
                return
            await ctx.typing()

        url = "https://xivapi.com" + result["Url"]
        params = {
            "columns": "ClassJobCategory.Name,DamageMag,DamagePhys,DefenseMag,DefensePhys,DelayMs,Description,IconHD,ItemUICategory.Name,LevelEquip,LevelItem,Name,Rarity,Stats"
        }
        async with self.bot.session.get(url, params=params) as r:
            if not r.ok:
                return await ctx.reply(f"XIV API Error: {r.status} {r.reason}")
            data = await r.json()

        name = data["Name"]
        category = data["ItemUICategory"]["Name"]
        icon_url = "https://xivapi.com" + data["IconHD"]
        # rarity = item_rarity[data["Rarity"]]

        item_level = data["LevelItem"]
        job_category = data["ClassJobCategory"]["Name"]
        equip_level = data["LevelEquip"]

        description = data["Description"].replace("\n\n\n\n", "\n\n")

        mag_dmg = ("Magic Damage", int(data["DamageMag"]))
        phys_dmg = ("Damage", int(data["DamagePhys"]))
        dmg = max(mag_dmg, phys_dmg, key=lambda x: x[1])
        mag_def = ("Magic Defense", int(data["DefenseMag"]))
        phys_def = ("Defense", int(data["DefensePhys"]))

        main_stats = [dmg, mag_def, phys_def]
        main_stats = [stat for stat in main_stats if stat[1] > 0]
        main_stats.sort(key=lambda x: x[0])
        if int(data["DelayMs"]):
            main_stats.append(("Delay", round(int(data["DelayMs"]) / 1000, 2)))

        if data["Stats"]:
            bonuses = [(re.sub("([A-Z]+)", r" \1", k), v["NQ"]) for k, v in data["Stats"].items()]
        else:
            bonuses = []

        embed = discord.Embed(title=name, color=0x293C66)
        embed.set_thumbnail(url=icon_url)
        embed.set_author(
            name="Eorzea Database",
            icon_url="https://img.finalfantasyxiv.com/lds/h/0/U2uGfVX4GdZgU1jASO0m9h_xLg.png",
        )
        desc = f"{category}\nItem Level **{item_level}**\n\n{job_category or 'All Classes'}\nLv. **{equip_level}**\n\n"

        if description:
            desc += f"{description}\n\n"

        for bonus in bonuses:
            desc += f"{bonus[0]}: **+{bonus[1]}**\n"

        embed.description = desc

        for stat in main_stats:
            embed.add_field(name=stat[0], value=stat[1])

        await ctx.reply(embed=embed)

    @xiv.command(aliases=["fr", "fashion"])
    async def fashionreport(self, ctx: commands.Context):
        """Displays the latest Fashion Report requirements."""
        headers = {"User-Agent": self.bot.real_user_agent}

        await ctx.typing()

        async with self.bot.session.get(
            f"{config.api_base_url}/xiv/kaiyoko", headers=headers, allow_redirects=False
        ) as r:
            title = r.headers.get("x-title")

        embed = discord.Embed(title=title, color=0xE7DFCE)
        embed.set_image(url=f"{config.api_base_url}/xiv/kaiyoko?includeMeta=false&t={utils.time()}")
        await ctx.reply(embed=embed)

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
