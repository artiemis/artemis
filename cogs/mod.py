from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
import pendulum
from discord.ext import commands

from utils.common import ArtemisError, parse_short_time

if TYPE_CHECKING:
    from bot import Artemis


class ShortTime(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> pendulum.DateTime:
        return parse_short_time(argument)


class Mod(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    def cog_check(self, ctx: commands.Context):
        if ctx.guild:
            return True
        raise commands.CheckFailure("This command cannot be used in private messages.")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str]):
        """Kicks a member with an optional reason."""
        if not reason:
            reason = f"Action done by {ctx.author} ({ctx.author.id})"
        else:
            reason = f"{ctx.author} ({ctx.author.id}): {reason}"
        await ctx.guild.kick(member, reason=reason)
        await ctx.reply(f"Successfully kicked {member}.")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str]):
        """Bans a member with an optional reason."""
        if not reason:
            reason = f"Action done by {ctx.author} ({ctx.author.id})"
        else:
            reason = f"{ctx.author} ({ctx.author.id}): {reason}"
        await ctx.guild.ban(member, reason=reason)
        await ctx.reply(f"Successfully banned {member}.")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        time: ShortTime,
        *,
        reason: Optional[str],
    ):
        """
        Mutes a member for a specific time with an optional reason.

        Usage examples:
        `{prefix}mute 555412947883524098 2h`
        `{prefix}mute Artemis 12h`
        `{prefix}mute Artemis 2d12h for being nosy`
        """
        max_timeout = pendulum.now("UTC").add(days=28)
        if time > max_timeout:
            raise ArtemisError("Mute time cannot exceed 28 days.")

        if not reason:
            reason = f"Action done by {ctx.author} ({ctx.author.id})"
        else:
            reason = f"{ctx.author} ({ctx.author.id}): {reason}"

        await member.timeout(time, reason=reason)
        return await ctx.reply(
            f"Successfully muted {member} until {discord.utils.format_dt(time)}."
        )

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        """
        Unmutes a member.
        """
        if not member.timed_out_until:
            return await ctx.reply("This member is not muted.")

        await member.timeout(None, reason=f"Action done by {ctx.author} ({ctx.author.id})")
        return await ctx.reply(f"Successfully unmuted {member}.")

    async def move_impl(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        *,
        no_messages: int = None,
        from_message_id: int = None,
        to_message_id: int = None,
        reason: str = None,
    ):
        await ctx.typing()

        webhooks = await channel.webhooks()
        webhook = discord.utils.get(webhooks, name="Artemis")

        if not webhook:
            webhook = await channel.create_webhook(
                name="Artemis", reason="Creating general-purpose webhook (called from $move)."
            )

        if no_messages:
            messages = [msg async for msg in ctx.history(limit=no_messages + 1)]
            messages = messages[::-1][:-1]
        else:
            messages = [
                msg
                async for msg in ctx.history(
                    after=discord.Object(from_message_id - 1),
                    before=discord.Object(to_message_id + 1),
                )
            ]

        for message in messages:
            embeds = []
            files = [await attachment.to_file() for attachment in message.attachments]

            if not message.content and message.author.bot:
                embeds = [embed for embed in message.embeds if embed.type == "rich"]

            if not message.content and not files and not embeds:
                continue

            await webhook.send(
                content=message.content,
                username=message.author.display_name,
                avatar_url=message.author.avatar.url,
                files=files,
                embeds=embeds,
            )
            await message.delete()

        await ctx.message.delete()

        if reason:
            await channel.send(
                f"Moved **{len(messages)}** messages from {ctx.channel.mention} for: `{reason}`",
                delete_after=30,
            )
        else:
            await channel.send(
                f"Moved **{len(messages)}** messages from {ctx.channel.mention}.", delete_after=30
            )

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def move(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        no_messages: int,
        *,
        reason: Optional[str],
    ):
        """Move `no_messages` to `channel` with an optional `reason`."""
        await self.move_impl(ctx, channel, no_messages=no_messages, reason=reason)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def move2(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        from_message_id: int,
        to_message_id: int,
        *,
        reason: Optional[str],
    ):
        """Move `from_message_id`-`to_message_id` messages to `channel` with an optional `reason`."""
        await self.move_impl(
            ctx,
            channel,
            from_message_id=from_message_id,
            to_message_id=to_message_id,
            reason=reason,
        )


async def setup(bot: Artemis):
    await bot.add_cog(Mod(bot))
