from typing import Any, List

import discord
from discord.ext import commands

from .common import trim


class BaseView(discord.ui.View):
    def __init__(self, ctx: commands.Context, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.ctx = ctx

    async def interaction_check(self, interaction):
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message(
            "This interaction cannot be controlled by you, sorry!", ephemeral=True
        )


class ConfirmView(BaseView):
    def __init__(self, ctx: commands.Context):
        super().__init__(ctx, timeout=60)
        self.result = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction, button):
        self.result = True
        self.stop()
        await self.message.delete()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction, button):
        self.result = False
        self.stop()
        await self.message.delete()

    async def prompt(self, message="Are you sure?", timeout_msg="You took too long!"):
        self.message = await self.ctx.send(message, view=self)
        if await self.wait():
            await self.message.edit(content=timeout_msg, view=None)
            return None
        return self.result


class ViewPages(BaseView):
    def __init__(self, ctx: commands.Context, items: List[Any], timeout: int = 180):
        super().__init__(ctx=ctx, timeout=timeout)
        self.items = items
        self.current_page = 0
        self.pages = len(self.items)
        self.use_last_and_first = self.pages > 2

    def get_kwargs(self, item: discord.Embed | str):
        if isinstance(item, discord.Embed):
            return {"embed": item}
        elif isinstance(item, str):
            return {"content": item}

    async def start(self):
        start_page = self.items[0]
        kwargs = self.get_kwargs(start_page)

        if self.pages == 1:
            return await self.ctx.send(**kwargs)
        elif not self.use_last_and_first:
            self.remove_item(self.first_page)
            self.remove_item(self.last_page)

        self.update_labels()
        self.message = await self.ctx.send(**kwargs, view=self)

    async def update_view(self, interaction: discord.Interaction):
        item = self.items[self.current_page]
        kwargs = self.get_kwargs(item)
        self.update_labels()

        if interaction.response.is_done():
            if self.message:
                await self.message.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    def update_labels(self):
        self.current_page_display.label = f"{self.current_page + 1}/{self.pages}"
        if self.use_last_and_first:
            self.first_page.disabled = self.current_page == 0
            self.last_page.disabled = (self.current_page + 1) >= self.pages
        self.next_page.disabled = False
        self.previous_page.disabled = False

        if (self.current_page + 1) >= self.pages:
            self.next_page.disabled = True
        elif self.current_page == 0:
            self.previous_page.disabled = True

    @discord.ui.button(label="◀◀", style=discord.ButtonStyle.blurple)
    async def first_page(self, interaction, button):
        self.current_page = 0
        await self.update_view(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.blurple)
    async def previous_page(self, interaction, button):
        if self.current_page != 0:
            self.current_page -= 1
            await self.update_view(interaction)

    @discord.ui.button(label="PH", style=discord.ButtonStyle.gray, disabled=True)
    async def current_page_display(self, interaction, button):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction, button):
        if not (self.current_page + 1) >= self.pages:
            self.current_page += 1
            await self.update_view(interaction)

    @discord.ui.button(label="▶▶", style=discord.ButtonStyle.blurple)
    async def last_page(self, interaction, button):
        self.current_page = self.pages - 1
        await self.update_view(interaction)

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None)


class BaseDropdown(discord.ui.Select):
    view: BaseView

    def __init__(self, items: list, label_key, description_key, placeholder: str, max_values: int):
        self.items = items

        options = []
        for i, item in enumerate(self.items[:25]):
            options.append(
                discord.SelectOption(
                    label=trim(label_key(item), 100),
                    description=trim(description_key(item), 100) if description_key else None,
                    value=str(i),
                )
            )
        super().__init__(placeholder=placeholder, options=options, max_values=max_values)

    async def callback(self, interaction: discord.Interaction):
        if self.max_values > 1:
            self.view.result = [self.items[int(i)] for i in self.values]
        else:
            result_idx = int(self.values[0])
            self.view.result = self.items[result_idx]
        self.view.stop()
        await self.view.message.delete()


class DropdownView(BaseView):
    def __init__(
        self,
        ctx,
        items,
        label_key,
        description_key=None,
        placeholder="Choose one...",
        max_values=1,
        chunk: bool = False,
    ):
        super().__init__(ctx, timeout=60)
        if chunk:
            items = items[: 5 * 25]
            for i in range(0, len(items), 25):
                chunk = items[i : i + 25]
                self.add_item(
                    BaseDropdown(chunk, label_key, description_key, placeholder, len(chunk))
                )
        else:
            self.add_item(BaseDropdown(items, label_key, description_key, placeholder, max_values))
        self.result = None

    async def prompt(self, message="Which one?", timeout_msg="You took too long!"):
        self.message = await self.ctx.send(message, view=self)
        if await self.wait():
            await self.message.edit(content=timeout_msg, view=None)
            return None
        return self.result
