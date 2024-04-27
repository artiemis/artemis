import asyncio
import contextlib
from json import JSONDecodeError
import logging
import os
import sys
import time
import traceback
from functools import cached_property
from typing import Optional

import aiohttp
import discord
import httpx
from discord import Webhook
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType

from .cogs import EXTENSIONS

from . import utils
from .utils import reddit
from .utils.api import API
from .utils.catbox import Catbox, Litterbox
from .utils.common import read_json, ArtemisError
from .utils.constants import TEMP_DIR
from .utils.unogs import uNoGS
from .utils import config


logging.basicConfig(
    level=logging.INFO,
    format="{levelname} - {name}: {message}",
    style="{",
    stream=sys.stdout,
)

log = logging.getLogger("artemis")
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("aiocache").setLevel(logging.ERROR)


class Artemis(commands.Bot):
    session: aiohttp.ClientSession
    httpx_session: httpx.AsyncClient

    def __init__(self):
        intents = discord.Intents(
            messages=True,
            message_content=True,
            guilds=True,
            members=True,
            emojis=True,
            reactions=True,
            voice_states=True,
        )

        try:
            status = read_json("data/status.json")
        except (JSONDecodeError, FileNotFoundError):
            status = {"name": None, "emoji": None}

        super().__init__(
            command_prefix=commands.when_mentioned_or(config.prefix),
            help_command=HelpEmbedded(command_attrs={"hidden": True}, verify_checks=False),
            intents=intents,
            allowed_mentions=discord.AllowedMentions(everyone=False, replied_user=False),
            owner_id=134306884617371648,
            activity=discord.CustomActivity(name=status["name"], emoji=status["emoji"]),
        )

        self.start_time = time.perf_counter()
        self.invite = discord.utils.oauth_url(
            client_id=555412947883524098, permissions=discord.Permissions(8)
        )

        self.user_agent: str = config.user_agent
        self.real_user_agent: str = config.real_user_agent
        self.keys = config.keys

        self.pink = discord.Colour(0xFFCFF1)
        self.invisible = discord.Colour(0x2F3136)

    async def maybe_send_restarted(self):
        restart = TEMP_DIR / "restart"
        if restart.exists():
            chid, _, mid = restart.read_text().partition("-")
            restart.unlink()

            with contextlib.suppress(Exception):
                ch = await self.fetch_channel(int(chid))
                msg = await ch.fetch_message(int(mid))
                await msg.add_reaction("☑️")

    async def setup_hook(self):
        # importing aiocache here so that its logger runs after our logging config
        from aiocache import Cache

        self.cache = Cache(Cache.MEMORY)
        self.session = aiohttp.ClientSession()
        self.httpx_session = httpx.AsyncClient(
            http2=True, follow_redirects=True, timeout=httpx.Timeout(60 * 3)
        )

        await self.load_extensions()

        self.api = API(self, self.keys.api)
        self.catbox = Catbox(self.keys.catbox, session=self.session)
        self.litterbox = Litterbox(session=self.session)
        self.unogs = uNoGS(session=self.session)
        self.reddit = reddit.Reddit(self.session)

        await self.maybe_send_restarted()

    async def load_extensions(self):
        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"

        await self.load_extension("jishaku")

        for extension in EXTENSIONS:
            await self.load_extension(extension)

    async def close(self):
        await self.session.close()
        await self.httpx_session.aclose()
        if hasattr(self, "db"):
            await self.db.close()
        await super().close()

    @cached_property
    def owner(self) -> Optional[discord.User]:
        return self.get_user(self.owner_id)

    def codeblock(self, text: str, lang: str = "py") -> str:
        return f"```{lang}\n{text}\n```"

    def get_message(self, msg_id: int):
        return (
            discord.utils.get(reversed(self.cached_messages), id=msg_id)
            if self.cached_messages
            else None
        )

    async def send_webhook(self, url: str, **kwargs):
        wh = Webhook.from_url(url=url, session=self.session)
        await wh.send(**kwargs)

    async def on_ready(self):
        log.info(f"Bot ready as {str(self.user)}.")

    async def on_disconnect(self):
        log.info("Disconnected.")

    async def on_resumed(self):
        log.info("Connection resumed.")

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        if isinstance(error, commands.CommandNotFound):
            msg = f"Command `{ctx.invoked_with}` not found."
            cmds = [command.name for command in self.commands if not command.hidden]
            aliases = [
                alias
                for command in self.commands
                for alias in command.aliases
                if not command.hidden
            ]

            found = utils.fuzzy_search_one(ctx.invoked_with, cmds + aliases, cutoff=70)
            if found:
                msg += f" Did you mean `{found}`?"
            return await ctx.reply(msg)
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.reply(f"Looks like you're missing the '{error.param.name}' parameter.")
        elif isinstance(error, commands.CommandOnCooldown):
            prefix = "This command is" if error.type == BucketType.default else "You're"
            return await ctx.reply(f"{prefix} on cooldown. Try again in {error.retry_after:.2f}s.")
        elif isinstance(error, discord.Forbidden):
            return await ctx.reply("This action is not possible due to a permission issue.")
        elif isinstance(error, (commands.CommandError, ArtemisError)):
            return await ctx.reply(str(error))

        log.error(f"Error in command {ctx.command} invoked by {str(ctx.author)} ({ctx.author.id})")
        traceback.print_exception(type(error), error, error.__traceback__)

        error_line = f"{error.__class__.__qualname__}: {utils.trim(str(error), 100)}"
        await ctx.reply(
            f"Oops! An unknown error occured.\nCode: `{error_line}`",
        )


class HelpEmbedded(commands.MinimalHelpCommand):
    context: commands.Context[Artemis]

    async def send_pages(self):
        destination = self.get_destination()
        for page in self.paginator.pages:
            embed = discord.Embed(title="Help", description=page, colour=self.context.bot.pink)
            await destination.send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog):
        commands = sorted(cog.get_commands(), key=lambda c: c.name)

        for command in commands:
            self.add_subcommand_formatting(command)

        channel = self.get_destination()
        for page in self.paginator.pages:
            embed = discord.Embed(
                title=f"{cog.qualified_name} {self.commands_heading}",
                description=page,
                colour=self.context.bot.pink,
            )
            await channel.send(embed=embed)

    async def send_group_help(self, group: commands.Group):
        if group.help:
            help = group.help.format(prefix=self.context.clean_prefix)
            self.paginator.add_line(help + "\n")

        commands = sorted(group.commands, key=lambda c: c.name)

        self.paginator.add_line("**Subcommands**")
        for command in commands:
            self.add_subcommand_formatting(command)

        channel = self.get_destination()
        for page in self.paginator.pages:
            embed = discord.Embed(
                title=self.get_command_signature(group),
                description=page,
                color=self.context.bot.pink,
            )
            await channel.send(embed=embed)

    async def send_command_help(self, command: commands.Command):
        help = ""
        if command.help:
            help = command.help.format(prefix=self.context.clean_prefix)
        embed = discord.Embed(
            title=self.get_command_signature(command),
            description=help,
            colour=self.context.bot.pink,
        )
        alias = command.aliases
        if alias:
            embed.add_field(name="Aliases", value=", ".join(alias), inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)


async def main():
    TEMP_DIR.mkdir(exist_ok=True)

    async with Artemis() as bot:
        await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("SIGINT received, closing.")
