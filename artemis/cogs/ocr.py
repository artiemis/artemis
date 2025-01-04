from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Literal, Optional

import discord
from discord.ext import commands

import discord.ext
import discord.ext.commands

from .. import utils
from ..utils.common import ArtemisError, compress_image, get_reply
from ..utils.constants import TESSERACT_LANGUAGES
from ..utils.flags import Flags, OCRFlags, OCRTranslateFlags
from ..utils.iso_639 import get_language_name

if TYPE_CHECKING:
    from ..bot import Artemis


class OCR(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    async def ocr_impl(
        self,
        ctx: commands.Context,
        flags: OCRFlags | OCRTranslateFlags | None,
        translate: Literal["gt", "deepl"] | None = None,
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

        if url or ctx.message.attachments:
            message = ctx.message
        else:
            message = await get_reply(ctx)

        if not message:
            raise ArtemisError("Could not find any images.")

        image = await utils.get_file_from_attachment_or_url(
            ctx, message, url, ["image/jpeg", "image/png"]
        )

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
            assert cmd
            await cmd(ctx, flags=flags)
        else:
            if len(text) > 2000 - 8:
                return await ctx.reply(file=discord.File(StringIO(text), "ocr.txt"))
            await ctx.reply(self.bot.codeblock(text, ""))

    async def yandex_impl(self, ctx: commands.Context[Artemis], url: str | None):
        await ctx.typing()

        if url or ctx.message.attachments:
            message = ctx.message
        else:
            message = await get_reply(ctx)

        if not message:
            raise ArtemisError("Could not find any images.")

        image = await utils.get_file_from_attachment_or_url(
            ctx, message, url, ["image/jpeg", "image/png"]
        )

        try:
            image = await compress_image(image, size=1000)
            image = image.getvalue()
        except Exception as e:
            raise ArtemisError(f"Could not compress image: {e}") from e

        result = await self.bot.api.yandex_ocr(image, "image/jpeg")
        return result

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

    @commands.command(
        aliases=["ocrdl"], usage="[source:auto] [lang:eng] [l:eng] [s:auto] [dest:en] [d:en] <url>"
    )
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
        OCR using Yandex.
        """
        result = await self.yandex_impl(ctx, url)

        assert result.detected_lang
        lang = get_language_name(result.detected_lang) or result.detected_lang
        msg = f"Detected language: {lang}\n" + self.bot.codeblock(result.text, "")

        if len(msg) > 2000:
            return await ctx.reply(
                content=f"Detected language: {lang}",
                file=discord.File(StringIO(result.text), "lens.txt"),
            )
        await ctx.reply(msg)

    @commands.command()
    @commands.max_concurrency(1)
    @commands.cooldown(1, 10, commands.BucketType.default)
    async def lensgt(self, ctx: commands.Context, *, url: Optional[str]):
        """
        OCR using Yandex and translation using Google Translate.
        """
        result = await self.yandex_impl(ctx, url)
        flags = Flags(text=result.text, source=None, dest=None)
        cmd = self.bot.get_command("gt")
        assert cmd
        await cmd(ctx, flags=flags)

    @commands.command(aliases=["lensdl", "lenstr"])
    @commands.max_concurrency(1)
    @commands.cooldown(1, 10, commands.BucketType.default)
    async def lensdeepl(self, ctx: commands.Context, *, url: Optional[str]):
        """
        OCR using Yandex and translation using DeepL.
        """
        result = await self.yandex_impl(ctx, url)
        flags = Flags(text=result.text, source=None, dest=None)
        cmd = self.bot.get_command("deepl")
        assert cmd
        await cmd(ctx, flags=flags)


async def setup(bot: Artemis):
    await bot.add_cog(OCR(bot))
