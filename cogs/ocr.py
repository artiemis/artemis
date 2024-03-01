from __future__ import annotations

import json
import mimetypes
import re
from io import StringIO
from typing import TYPE_CHECKING, Literal, Optional

import discord
import magic
from discord.ext import commands

import utils
from utils.common import ArtemisError
from utils.constants import TESSERACT_LANGUAGES
from utils.flags import Flags, OCRFlags, OCRTranslateFlags
from utils.iso_639 import get_language_name

if TYPE_CHECKING:
    from bot import Artemis


class OCR(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    async def ocr_impl(
        self,
        ctx: commands.Context,
        flags: OCRFlags | OCRTranslateFlags,
        translate: Literal["gt", "deepl"] = None,
    ):
        if flags:
            url = flags.url
            lang = flags.lang or "eng"
        else:
            url = None
            lang = "eng"

        await ctx.typing()

        for lang_code in lang.split("+"):
            if lang_code not in TESSERACT_LANGUAGES:
                msg = "Unsupported language code, list of supported languages:\n\n"
                msg += "\n".join(
                    (f"`{lang}` - {get_language_name(lang[:3])}" for lang in TESSERACT_LANGUAGES)
                )
                embed = discord.Embed(description=msg, color=discord.Color.red())
                return await ctx.reply(embed=embed)

        message = await utils.get_message_or_reference(ctx)
        image = await utils.get_attachment_or_url(ctx, message, url, ["image/jpeg", "image/png"])

        args = f"tesseract stdin stdout -l {lang}"
        result = await utils.run_cmd(args, input=image)
        stdout, stderr = result.stdout, result.stderr

        if not result.ok:
            return await ctx.reply(result.decoded)
        elif not stdout:
            return await ctx.reply(
                f"No recognized text output, stderr:\n{self.bot.codeblock(stderr.decode(), '')}"
            )

        text = stdout.decode("utf-8")

        if translate:
            if flags:
                flags.text = text
            else:
                flags = Flags(text=text, source=None, dest=None)
            cmd = self.bot.get_command(translate)
            await cmd(ctx, flags=flags)
        else:
            if len(text) > 2000 - 8:
                return await ctx.reply(file=discord.File(StringIO(text), "ocr.txt"))
            await ctx.reply(self.bot.codeblock(text, ""))

    async def lens_impl(self, ctx: commands.Context[Artemis], url: str) -> str:
        headers = {"User-Agent": self.bot.user_agent}
        cookies = {
            "CONSENT": "PENDING+137",
            "SOCS": "CAISHAgBEhJnd3NfMjAyMzEwMTItMF9SQzQaAnBsIAEaBgiA48GpBg",
        }
        final_data_re = r"\"(\w+)\",\[\[(\[\".*?\"\])\]"

        cur_time = utils.time("ms")
        upload_url = f"https://lens.google.com/v3/upload?hl=en&re=df&st={cur_time}&ep=gsbubb"

        await ctx.typing()

        message = await utils.get_message_or_reference(ctx)
        image = await utils.get_attachment_or_url(ctx, message, url, ["image/jpeg", "image/png"])

        content_type = magic.from_buffer(image, mime=True)
        ext = mimetypes.guess_extension(content_type)

        files = {"encoded_image": (f"image{ext}", image, content_type)}
        r = await ctx.bot.httpx_session.post(
            upload_url,
            files=files,
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
        )
        if r.is_error:
            print(r.text)
            raise ArtemisError(f"Google Lens Upload returned {r.status_code} {r.reason_phrase}")
        html = r.text

        match = re.search(final_data_re, html)
        if not match:
            if ctx.author.id == self.bot.owner.id:
                await ctx.send(file=utils.File(html, "lens.html"))
            raise ArtemisError("No text detected.")
        _lang, lines = match.groups()

        text = "\n".join(json.loads(lines))
        return text

    @commands.command(usage="[lang:eng] [l:eng] <url>")
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def ocr(self, ctx: commands.Context, *, flags: Optional[OCRFlags]):
        """
        OCR using tesseract 5.

        Default language: `eng` (English)
        You can specify multiple languages using `+` -> `eng+pol`.
        """
        await self.ocr_impl(ctx, flags)

    @commands.command(usage="[source:auto] [lang:eng] [l:eng] [s:auto] [dest:en] [d:en] <url>")
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def ocrgt(self, ctx: commands.Context, *, flags: Optional[OCRTranslateFlags]):
        """
        OCR using tesseract and translation using Google.
        Takes $translate and $ocr flags combined.
        """
        await self.ocr_impl(ctx, flags, translate="gt")

    @commands.command(usage="[source:auto] [lang:eng] [l:eng] [s:auto] [dest:en] [d:en] <url>")
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def ocrdeepl(self, ctx: commands.Context, *, flags: Optional[OCRTranslateFlags]):
        """
        OCR using tesseract and translation using DeepL.
        Takes $deepl and $ocr flags combined.
        """
        await self.ocr_impl(ctx, flags, translate="deepl")

    @commands.command()
    @commands.max_concurrency(1)
    @commands.cooldown(1, 10, commands.BucketType.default)
    async def lens(self, ctx: commands.Context, *, url: Optional[str]):
        """
        OCR using Google Lens.
        """
        text = await self.lens_impl(ctx, url)
        if len(text) > 2000 - 8:
            return await ctx.reply(file=discord.File(StringIO(text), "lens.txt"))
        await ctx.reply(self.bot.codeblock(text, ""))

    @commands.command(aliases=["ocrtr"])
    @commands.max_concurrency(1)
    @commands.cooldown(1, 10, commands.BucketType.default)
    async def lensgt(self, ctx: commands.Context, *, url: Optional[str]):
        """
        OCR using Google Lens and translation using Google Translate.
        """
        text = await self.lens_impl(ctx, url)
        flags = Flags(text=text, source=None, dest=None)
        cmd = self.bot.get_command("gt")
        await cmd(ctx, flags=flags)

    @commands.command(aliases=["lenstr"])
    @commands.max_concurrency(1)
    @commands.cooldown(1, 10, commands.BucketType.default)
    async def lensdeepl(self, ctx: commands.Context, *, url: Optional[str]):
        """
        OCR using Google Lens and translation using DeepL.
        """
        text = await self.lens_impl(ctx, url)
        flags = Flags(text=text, source=None, dest=None)
        cmd = self.bot.get_command("deepl")
        await cmd(ctx, flags=flags)


async def setup(bot: Artemis):
    await bot.add_cog(OCR(bot))
