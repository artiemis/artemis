from __future__ import annotations, unicode_literals

import json
import os
import typing
from base64 import b64decode
from io import StringIO
from typing import TYPE_CHECKING, Optional

import discord
import magic
from discord.ext import commands
from jishaku import codeblocks
import pendulum

from .. import utils
from ..utils.common import ArtemisError
from ..utils.constants import TEMP_DIR
from ..utils.views import BaseView

if TYPE_CHECKING:
    from ..bot import Artemis


class Owner(commands.Cog, command_attrs={"hidden": True}):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    async def cog_check(self, ctx: commands.Context):
        if ctx.author.id == self.bot.owner_id:
            return True
        raise commands.CheckFailure("You do not have permission to run this command.")

    @commands.group()
    async def dev(self, ctx: commands.Context):
        """Bot developer commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid subcommand passed.")

    @dev.command()
    async def load(self, ctx: commands.Context, extension: str):
        """Loads a cog."""
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await ctx.send(f"Loaded '{extension}.py'")
        except Exception as e:
            await ctx.send(e)

    @dev.command()
    async def unload(self, ctx: commands.Context, extension: str):
        """Unloads a cog."""
        try:
            await self.bot.unload_extension(f"cogs.{extension}")
            await ctx.send(f"Unloaded '{extension}.py'")
        except Exception as e:
            await ctx.send(e)

    @dev.command(name="reload")
    async def _reload(self, ctx: commands.Context, extension: Optional[str]):
        """Reloads a cog."""
        if not extension:
            try:
                for filename in os.listdir("./cogs"):
                    if filename.endswith(".py") and filename != "__init__.py":
                        await self.bot.reload_extension(f"cogs.{filename[:-3]}")
                await ctx.send("Reloaded all cogs.")
            except Exception as e:
                await ctx.send(e)
        else:
            try:
                await self.bot.reload_extension(f"cogs.{extension}")
                await ctx.send(f"Reloaded '{extension}.py'")
            except Exception as e:
                await ctx.send(e)

    @commands.command(aliases=["r"])
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        await ctx.message.add_reaction("🔄")
        (TEMP_DIR / "restart").write_text(f"{ctx.channel.id}-{ctx.message.id}")
        await self.bot.close()

    @commands.command(aliases=["u"])
    @commands.is_owner()
    async def update(self, ctx: commands.Context[Artemis]):
        class RestartView(BaseView):
            message: discord.Message

            def __init__(self, ctx: commands.Context):
                super().__init__(ctx, timeout=60)

            @discord.ui.button(label="Restart", style=discord.ButtonStyle.danger)
            async def on_restart(self, interaction: discord.Interaction, button):
                await interaction.response.edit_message(view=None)
                await self.message.add_reaction("🔄")
                (TEMP_DIR / "restart").write_text(f"{self.message.channel.id}-{self.message.id}")
                await self.ctx.bot.close()

            async def on_timeout(self):
                await self.message.edit(view=None)

        await ctx.typing()

        res = await utils.run_cmd("git pull")
        output = res.decoded

        embed = discord.Embed(
            description=self.bot.codeblock(output, ""),
            timestamp=pendulum.now(),
            color=discord.Color.green() if res.ok else discord.Color.red(),
        )

        if res.ok and output.strip() != "Already up to date.":
            view = RestartView(ctx)
            view.message = await ctx.reply(embed=embed, view=view)
            return
        await ctx.reply(embed=embed)

    @dev.command()
    @commands.is_owner()
    async def status(
        self, ctx: commands.Context, emoji: Optional[discord.Emoji], *, name: Optional[str]
    ):
        await self.bot.change_presence(activity=discord.CustomActivity(name=name, emoji=emoji))
        with open("data/status.json", "w") as f:
            json.dump({"name": name, "emoji": emoji}, f)
        await ctx.message.add_reaction("☑️")

    @dev.command()
    @commands.guild_only()
    async def sync(
        self,
        ctx: commands.Context,
        guilds: commands.Greedy[discord.Object],
        spec: Optional[typing.Literal["~", "*", "^"]] = None,
    ) -> None:
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @dev.command()
    async def spy(self, ctx: commands.Context, *, code: str):
        silencer = """
try:
  asyncio.create_task(ctx.message.delete())
except Exception:
  pass
"""

        if code.startswith("```py"):
            code = code[:5] + silencer + code[5:]
        else:
            code = silencer + code

        jsk_py = self.bot.get_command("jsk py")
        await jsk_py(ctx, argument=codeblocks.codeblock_converter(code))

    @dev.command()
    async def http(self, ctx: commands.Context, url: str):
        """Debugs HTTP requests."""
        url = url.strip("<>")
        await ctx.typing()
        headers = {"User-Agent": self.bot.user_agent}
        async with self.bot.session.get(url, headers=headers, allow_redirects=False) as r:
            headers = "\n".join([f"{k}: {v}" for k, v in r.headers.items()])
            m = f"HTTP/1.1 {r.status} {r.reason}\n{headers}"
        if len(m) <= 2000:
            await ctx.send(self.bot.codeblock(m, "http"))
        else:
            m = StringIO(m)
            await ctx.send(file=discord.File(m, "headers.http"))

    @dev.command()
    async def mime(self, ctx: commands.Context, url: str):
        """Check magic bytes of a file to determine its format."""
        url = url.strip("<>")
        headers = {"User-Agent": self.bot.user_agent}

        await ctx.typing()

        async with self.bot.session.get(url, headers=headers) as r:
            mime = None
            content_type = r.content_type

            buff = await r.content.read(4096)
            if not buff:
                return await ctx.reply("No data in body.")

            mime = magic.from_buffer(buff)
            content_type = content_type or magic.from_buffer(buff, mime=True)
            return await ctx.reply(f"{mime}\n`{content_type}`")

    @dev.command()
    async def say(self, ctx: commands.Context, channel: Optional[discord.TextChannel], *, msg: str):
        """Says message as the bot."""
        if not channel:
            try:
                await ctx.message.delete()
            except Exception:
                pass
            await ctx.send(msg)
        else:
            await channel.send(msg)

    @dev.command()
    async def delete(self, ctx: commands.Context):
        """Deletes the replied to message."""
        try:
            await ctx.message.reference.cached_message.delete()
            await ctx.message.delete()
        except Exception:
            pass

    @dev.command()
    async def catdel(self, ctx: commands.Context, *files):
        """Deletes catbox files."""
        files = " ".join([f.strip("<>").split("/")[-1] for f in files])
        resp = await self.bot.catbox.delete(files)
        await ctx.reply(resp)

    @dev.command()
    async def ping(self, ctx: commands.Context, host: str):
        """Pings a host."""
        async with ctx.typing():
            result = await utils.run_cmd(f"ping -n -c 3 {host}")
            cb_wrapped = self.bot.codeblock(result.decoded, "c")
        await ctx.send(cb_wrapped)

    @dev.command(name="b64decode")
    async def _b64decode(self, ctx: commands.Context, data: str):
        """Decodes base64 data."""
        data = b64decode(data + "==")
        try:
            data = data.decode()
        except Exception:
            pass
        return await ctx.send(data)

    @dev.command()
    async def mp4ify(self, ctx: commands.Context, *, url: utils.URL):
        """Makes the video playable in Discord and browsers."""
        args = f'ffmpeg -hide_banner -loglevel error -headers "User-Agent: {self.bot.user_agent}" -i "{url}" -pix_fmt yuv420p -f mp4 -movflags frag_keyframe+empty_moov -'
        filename = url.split("/")[-1].split("?")[0].split("#")[0]
        if not filename.endswith(".mp4"):
            filename += ".mp4"

        async with ctx.typing():
            try:
                file = await utils.run_cmd_to_file(args, filename)
            except Exception as err:
                return await ctx.reply(str(err).split("pipe:")[0])

        await ctx.reply(file=file)

    @dev.command()
    async def oggify(self, ctx: commands.Context, *, url: utils.URL):
        """Makes the audio playable in Discord and browsers."""
        args = f'ffmpeg -hide_banner -loglevel error -headers "User-Agent: {self.bot.user_agent}" -i "{url}" -c:a libopus -vbr on -b:a 128k -f opus -'
        filename = url.split("/")[-1].split("?")[0].split("#")[0]
        basename = filename.split(".")[0]
        filename = basename + ".ogg"

        async with ctx.typing():
            try:
                file = await utils.run_cmd_to_file(args, filename)
            except Exception as err:
                return await ctx.reply(str(err).split("pipe:")[0])

        await ctx.reply(file=file)

    async def handle_tempo_conversion(
        self, ctx: commands.Context, target: str, url: str, rubberband: bool
    ):
        factor = None
        if target == "pal":
            factor = "1.04271"
        elif target == "ntsc":
            factor = "0.95904"
        else:
            raise ArtemisError("Invalid target.")

        if rubberband:
            filters = f"rubberband=tempo={factor}:pitch={factor}"
        else:
            filters = f"atempo={factor}"

        args = f'ffmpeg -hide_banner -loglevel error -headers "User-Agent: {self.bot.user_agent}" -i "{url}" -c:a libopus -vbr on -b:a 128k -af "{filters}" -f opus -'

        filename = url.split("/")[-1].split("?")[0].split("#")[0]
        basename = filename.split(".")[0]
        filename = f"{basename}_{target.upper()}.ogg"

        async with ctx.typing():
            try:
                file = await utils.run_cmd_to_file(args, filename)
            except Exception as err:
                return await ctx.reply(str(err).split("pipe:")[0])

        await ctx.reply(file=file)

    @dev.command()
    async def ntsctopal(self, ctx: commands.Context, url: utils.URL, rubberband: bool = True):
        """NTSC (23.976) to PAL (25) audio conversion with optional pitch correction."""
        await self.handle_tempo_conversion(ctx, "pal", url, rubberband=rubberband)

    @dev.command()
    async def paltontsc(self, ctx: commands.Context, url: utils.URL, rubberband: bool = True):
        """PAL (25) to NTSC (23.976) audio conversion with optional pitch correction."""
        await self.handle_tempo_conversion(ctx, "ntsc", url, rubberband=rubberband)


async def setup(bot: Artemis):
    await bot.add_cog(Owner(bot))
