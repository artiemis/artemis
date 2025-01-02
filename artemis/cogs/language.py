from __future__ import annotations

import asyncio
import re
from io import BytesIO
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote, quote_plus, unquote

import discord
import gtts
import pendulum
from aiogoogletrans import LANGUAGES as GT_LANGUAGES
from aiogoogletrans import Translator
from bs4 import BeautifulSoup, Tag
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt

from .. import utils
from ..utils import iso_639
from ..utils.common import (
    ArtemisError,
    Stopwatch,
    get_reply,
    read_json,
)
from ..utils.constants import (
    GT_LANGUAGES_EXTRAS,
)
from ..utils.flags import TranslateFlags, TTSFlags
from ..utils.views import ViewPages

if TYPE_CHECKING:
    from ..bot import Artemis

# Mod aiogoogletrans
GT_LANGUAGES.update(GT_LANGUAGES_EXTRAS)
translator = Translator()
translator.lock = asyncio.Lock()

# Load toki pona data
nimi = read_json("data/nimi.json")

nimi_lookup = {entry["word"]: entry for entry in nimi}
nimi_reverse_lookup = {entry["definition"]: entry for entry in nimi}


# Translation slash commands
@app_commands.context_menu(name="Translate (DeepL)")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def deepl_slash(interaction: discord.Interaction[Artemis], message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    content = message.content
    if not content:
        return await interaction.followup.send("No text detected.", ephemeral=True)

    languages = interaction.client.deepl.languages

    result = None
    result_src = None
    result_dest = "en"
    billed_characters = None

    try:
        result = await interaction.client.deepl.translate(content, "auto", "EN")
        result_src = result.src.lower()
        billed_characters = result.billed_characters
    except Exception as err:
        raise ArtemisError(f"DeepL Error: `{err}`")

    display_src = languages.get(result_src) or result_src
    display_dest = languages.get(result_dest) or result_dest
    translation = result.translation

    embed = discord.Embed(colour=0x0F2B46)
    embed.set_author(
        name="DeepL",
        icon_url="https://www.google.com/s2/favicons?domain=deepl.com&sz=64",
    )
    embed.add_field(name=f"From {display_src} to {display_dest}", value=translation)
    if billed_characters:
        embed.set_footer(text=f"Billed characters: {billed_characters}")
    await interaction.followup.send(embed=embed, ephemeral=True)


@app_commands.context_menu(name="Translate (Google)")
@app_commands.allowed_installs(guilds=False, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def gt_slash(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    content = message.content
    if not content:
        return await interaction.followup.send("No text detected.", ephemeral=True)

    async with translator.lock:
        try:
            result = await translator.translate(content, src="auto", dest="en")
        except ValueError as err:
            return await interaction.followup.send(f"Error: {err}", ephemeral=True)

    src = GT_LANGUAGES[result.src.lower()].title()
    translated = result.text

    embed = discord.Embed(description=translated, color=0x4B8CF5)
    embed.set_footer(
        text=f"Translated from {src} by Google",
        icon_url="https://upload.wikimedia.org/wikipedia/commons/d/db/Google_Translate_Icon.png",
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


class Language(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

        for menu in (deepl_slash, gt_slash):
            self.bot.tree.add_command(menu)

    @commands.command()
    async def langname(self, ctx: commands.Context, code: str):
        """
        Converts language code to language name.
        Supports ISO `639-1` to `639-3`.
        """
        found = iso_639.get_language_name(code)
        if not found:
            return await ctx.reply("Language code not found.")

        m = f"Code: **{code.lower()}**\nName: **{found}**"
        await ctx.reply(m)

    @commands.command()
    async def langcode(self, ctx: commands.Context, *, name: str):
        """
        Converts language name to language codes in ISO `639-1` to `639-3`.
        """
        found = iso_639.get_language_code(name)
        if not found:
            return await ctx.reply("Language name not found.")

        codes = []
        for code in found:
            m = f"Name: **{code['name']}**\n"
            m += f"part3: **{code['part3']}**\n"
            if code["part2b"]:
                m += f"part2b: **{code['part2b']}**\n"
            if code["part2t"]:
                m += f"part2t: **{code['part2t']}**\n"
            if code["part1"]:
                m += f"part1: **{code['part1']}**\n"
            codes.append(m)

        view = ViewPages(ctx, codes)
        await view.start()

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def jisho(self, ctx: commands.Context, *, query: str):
        """Look up a word in Jisho (JP-EN / EN-JP dictionary)."""

        base = "https://jisho.org/api/v1/search/words?keyword="
        payload = base + quote_plus(query)

        await ctx.typing()
        async with self.bot.session.get(payload) as r:
            json = await r.json()
            data = json["data"]
        if not data:
            return await ctx.reply("No results found.")

        embeds = []
        for meaning in data:
            slug = meaning["slug"]

            word = meaning["japanese"][0].get("word")
            reading = meaning["japanese"][0].get("reading")

            furigana = None
            if word and reading:
                furigana = reading
                source = reading
            else:
                source = word or reading

            romaji = utils.romajify(source)

            embed = discord.Embed(
                title=word or reading,
                description=f"{furigana or ''}\n{romaji}",
                url=f"https://jisho.org/word/{quote(slug)}",
                colour=0x56D926,
            )
            embed.set_author(name="Jisho", icon_url="https://i.imgur.com/SO4IGvY.png")

            for sense in meaning["senses"]:
                parts_of_speech = ", ".join(sense["parts_of_speech"])
                definition = ", ".join(sense["english_definitions"])
                tags = ", ".join(sense["tags"]) or ""
                tags = tags if "Usually written using kana alone" not in tags else ""
                name = f"{parts_of_speech}\n{tags}".strip()

                if "Wikipedia definition" in parts_of_speech:
                    wiki = sense["links"][0]
                    definition = f"[{definition}]({wiki['url']})"

                embed.add_field(name=name or "Special", value=definition, inline=False)
            embeds.append(embed)

        view = ViewPages(ctx, embeds)
        await view.start()

    @commands.command(usage="[source:auto] [s:auto] [dest:en] [d:en] <text>")
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def gt(self, ctx: commands.Context, *, flags: TranslateFlags | None):
        """
        Translation using Google Translate.

        Optional flags:
        `source` or `s` - Source language, defaults to `auto`.
        `dest` or `d` - Target (destination) language, defaults to `en`.

        Example usage:
        `{prefix}gt Hej, co tam?`
        `{prefix}gt s:pl d:en Hey, what's up?`
        """
        text = None
        src = "auto"
        dest = "en"

        if flags:
            text = flags.text
            src = flags.source or src
            dest = flags.dest or dest

        reply = await get_reply(ctx)
        if reply and not text:
            text = reply.content

        if not text:
            raise ArtemisError("No text provided.")

        async with translator.lock:
            try:
                result = await translator.translate(text, src=src, dest=dest)
            except ValueError as err:
                return await ctx.reply(f"Error: {err}")

        src = result.src.lower()
        try:
            src = GT_LANGUAGES[src].title()
        except Exception:
            pass
        dest = GT_LANGUAGES[result.dest.lower()].title()
        translation = result.text

        if len(translation) > 1024:
            buff = f"--- From {src} to {dest} ---\n{translation}".encode("utf-8")
            buff = BytesIO(buff)
            file = discord.File(buff, f"{src}-{dest}.txt")

            return await ctx.reply(
                "The translation could not fit on the screen, so here's a file:",
                file=file,
            )

        embed = discord.Embed(colour=0x4B8CF5)
        embed.set_author(
            name="Google Translate",
            icon_url="https://upload.wikimedia.org/wikipedia/commons/d/db/Google_Translate_Icon.png",
        )
        embed.add_field(name=f"From {src} to {dest}", value=translation)
        await ctx.reply(embed=embed)

    @commands.group(
        invoke_without_command=True, usage="[source:auto] [s:auto] [dest:en] [d:en] <text>"
    )
    @commands.max_concurrency(1)
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def deepl(self, ctx: commands.Context, *, flags: TranslateFlags | None):
        """
        Translation using DeepL.

        Optional flags:
        `source` or `s` - Source language, defaults to `auto`.
        `dest` or `d` - Target (destination) language, defaults to `en`.

        Example usage:
        `{prefix}deepl Hej, co tam?`
        `{prefix}trd s:pl d:en Hey, what's up?`
        """
        text = None
        src = "auto"
        dest = "en"

        if flags:
            text = flags.text
            src = flags.source or src
            dest = flags.dest or dest

        reply = await get_reply(ctx)
        if reply and not text:
            text = reply.content

        if not text:
            raise ArtemisError("No text provided.")

        await ctx.typing()

        languages = self.bot.deepl.languages

        if src != "auto" and src not in languages or dest not in languages:
            msg = "Unsupported language code, list of supported languages:\n\n"
            msg += "\n".join((f"`{k}` - {v}" for k, v in languages.items()))
            embed = discord.Embed(description=msg, color=discord.Color.red())
            return await ctx.reply(embed=embed)

        result = None
        result_src = None
        result_dest = dest.lower()
        billed_characters = None

        try:
            result = await self.bot.deepl.translate(text, src.upper(), dest.upper())
            result_src = result.src.lower()
            billed_characters = result.billed_characters
        except Exception as err:
            raise ArtemisError(f"DeepL Error: `{err}`")

        display_src = languages.get(result_src) or result_src
        display_dest = languages.get(result_dest) or result_dest
        translation = result.translation

        if len(translation) > 1024:
            buff = f"--- From {display_src} to {display_dest} ---\n{translation}".encode("utf-8")
            buff = BytesIO(buff)
            file = discord.File(buff, f"{display_src}-{display_dest}.txt")

            return await ctx.reply(
                "The translation could not fit on the screen, so here's a file:",
                file=file,
            )

        embed = discord.Embed(colour=0x0F2B46)
        embed.set_author(
            name="DeepL",
            icon_url="https://www.google.com/s2/favicons?domain=deepl.com&sz=64",
        )
        embed.add_field(name=f"From {display_src} to {display_dest}", value=translation)
        if billed_characters:
            embed.set_footer(text=f"Billed characters: {billed_characters}")
        await ctx.reply(embed=embed)

    @deepl.command(aliases=["quota"])
    async def usage(self, ctx: commands.Context):
        """
        Returns the character quota left for the month.
        """
        await ctx.typing()
        usage = await self.bot.deepl.usage()
        reset = pendulum.now("UTC").add(months=1).replace(day=2, hour=16, minute=30, second=0)
        await ctx.reply(
            f"Characters used: **{usage.character_count}**\nCharacters left: **{usage.character_limit - usage.character_count}**\nQuota resets {format_dt(reset, "R")}."
        )

    @commands.command(usage="[lang:en] [l:en] <text>")
    @commands.max_concurrency(1)
    async def tts(self, ctx: commands.Context, *, flags: TTSFlags):
        """
        Make Google TTS say some stuff.

        Optional flags:
        `lang` or `l` - Two-letter language code.
        Defaults to English (`en`).
        [Supported languages.](https://mystb.in/RemovalNilVariance.json)

        Example usage:
        `{prefix}tts apple`
        `{prefix}tts apple cider`
        `{prefix}tts l:pl jabłko`
        `{prefix}tts l:de apfel`
        """
        text = flags.text
        lang = flags.lang or "en"

        if lang not in gtts.lang.tts_langs().keys():
            return await ctx.reply("Sorry, I couldn't find that language!")
        elif not text:
            return await ctx.reply("No text provided.")

        await ctx.typing()

        mp3_fp = BytesIO()
        filename = f"{ctx.author.display_name}-TTS-{lang}.mp3"

        with Stopwatch() as sw:
            tts = await asyncio.to_thread(gtts.gTTS, text, lang=lang)
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)

        discord_file = discord.File(mp3_fp, filename)

        diff = round(sw.result, 2)
        await ctx.reply(content=f"Finished in {diff}s.", file=discord_file)

    @commands.command(aliases=["ud"])
    async def urban(self, ctx: commands.Context, *, phrase):
        """Look up a phrase in the Urban Dictionary."""
        # thanks, Danny
        ref_re = re.compile(r"(\[(.+?)\])")

        def repl(m):
            word = m.group(2)
            return f'[{word}](http://{word.replace(" ", "-")}.urbanup.com)'

        await ctx.typing()

        params = {"term": phrase}
        async with self.bot.session.get(
            "https://api.urbandictionary.com/v0/autocomplete-extra", params=params
        ) as r:
            data = await r.json()

        results = data["results"]
        if not results:
            raise ArtemisError("No results found.")

        params = {"term": results[0]["term"]}
        async with self.bot.session.get(
            "http://api.urbandictionary.com/v0/define", params=params
        ) as r:
            data = await r.json()

        results = data["list"]
        if not results:
            raise ArtemisError("No results found.")

        embeds = []
        for result in results:
            title = result["word"]
            definition = ref_re.sub(repl, result["definition"])
            example = ref_re.sub(repl, result["example"])
            permalink = result["permalink"]
            written_on = pendulum.parse(result["written_on"][0:10], tz="UTC")

            if not example:
                example = "No example provided."

            embed = discord.Embed(
                title=title,
                description=utils.trim(definition, 4096),
                url=permalink,
                color=0x134FE6,
                timestamp=written_on,
            )
            embed.add_field(name="Example:", value=utils.trim(example, 1024), inline=False)
            embed.set_footer(
                text=f"{result['thumbs_up']} 👍 {result['thumbs_down']} 👎 • Written by {result['author']}"
            )
            embed.set_author(name="Urban Dictionary", icon_url="https://i.imgur.com/2NDCme4.png")
            embeds.append(embed)

        view = ViewPages(ctx, embeds)
        await view.start()

    @commands.command(usage="<wyraz/word>")
    async def sjp(self, ctx: commands.Context, *, word: str):
        """
        :flag_pl:  Wyszukaj podany wyraz w słowniku języka polskiego ze strony `sjp.pl`.
        Wpisy bez definicji są zastąpione źródłem, na jakie powołuje się strona.

        :flag_gb:  Look up a word in the Polish dictionary sourced from `sjp.pl`.
        Entries with missing definitions are replaced by a source referenced by the website.
        """
        headers = {"User-Agent": self.bot.user_agent}
        SJP_ICON = "https://i.imgur.com/b4JLozn.png"

        params = {"q": word}
        async with self.bot.session.get(
            "https://sjp.pl/slownik/s/", params=params, headers=headers
        ) as r:
            res = await r.json(content_type=None)
        if not res["d"]:
            return await ctx.reply(
                f":flag_pl:  `{word}` nie występuje w słowniku.\n:flag_gb:  `{word}` not found in the dictionary."
            )

        word = quote(res["d"][0])
        url = f"https://sjp.pl/{word}"
        async with self.bot.session.get(url, headers=headers) as r:
            html = await r.text()
        soup = BeautifulSoup(html, "lxml")

        for element in soup.find_all("br"):
            element.append("\n")

        entries = []
        meanings = soup.select("h1")
        for meaning in meanings:
            word = meaning.text
            original = None
            definitions = []
            dictionary = None

            for element in meaning.next_siblings:
                if element in meanings:
                    break
                if not isinstance(element, Tag):
                    continue
                if "margin: .5em" in element.get("style", ""):
                    definitions = [
                        re.sub(r"\d\.\s", "", defi).rstrip(";") for defi in element.text.split("\n")
                    ]
                orig = element.select_one(".lc")
                if orig:
                    original = orig.text if orig.text != word else None
                td = element.select_one("td")
                if td:
                    dictionary = td.text
            entries.append(
                {
                    "word": word,
                    "root": original,
                    "definitions": definitions,
                    "dictionary": dictionary,
                }
            )

        embed = discord.Embed(colour=0x2266CC).set_author(name="SJP.pl", icon_url=SJP_ICON, url=url)
        for entry in entries:
            word = entry["root"] or entry["word"]
            definitions = entry["definitions"]

            if not definitions:
                if entry["dictionary"]:
                    definition = f"Występowanie: `{entry['dictionary']}`"
                else:
                    definition = "Brak definicji / No definition"
            else:
                definition = ""
                for idx, defi in enumerate(entry["definitions"], start=1):
                    definition += f"`{idx}.` {defi}\n"
            embed.add_field(name=word, value=definition, inline=False)

        await ctx.reply(embed=embed)

    @commands.command()
    async def nimi(self, ctx: commands.Context, *, query: str):
        """toki pona word list supporting toki pona and English lookup."""
        spreadsheet = "https://docs.google.com/spreadsheets/d/1t-pjAgZDyKPXcCRnEdATFQOxGbQFMjZm-8EvXiQd2Po/edit#gid=0"
        icon = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Toki_Pona_flag.svg/320px-Toki_Pona_flag.svg.png"
        query = query.strip().replace("  ", " ").lower()

        # try word lookup
        entries = [nimi_lookup.get(query)]

        # try definition lookup
        if not entries[0]:
            entries.pop()
            for definition, entry in nimi_reverse_lookup.items():
                if re.search(rf"\b{query}\b", definition.lower()):
                    entries.append(entry)

        if not entries:
            return await ctx.reply("No results found.")

        embeds = []
        for entry in entries:
            embed = discord.Embed(
                title=entry["word"],
                description=entry["definition"],
                url=spreadsheet,
                color=0xFEFEFE,
            )
            embed.set_footer(text="nimi ale pona (2nd ed.)", icon_url=icon)

            for k, v in entry.items():
                if not v or k in ("word", "definition"):
                    continue
                k = k.title() if k != "creator(s)" else "Creator(s)"
                embed.add_field(name=k, value=v, inline=False)
            embeds.append(embed)

        view = ViewPages(ctx, embeds)
        await view.start()


async def setup(bot: Artemis):
    await bot.add_cog(Language(bot))
