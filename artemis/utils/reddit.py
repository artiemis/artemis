from __future__ import annotations
from functools import cached_property

import html
import random
import re
from typing import Any, Literal, Optional

import discord
import pendulum
from aiohttp import ClientSession
from humanize import intcomma
from yt_dlp.utils import random_user_agent

from . import utils
from .common import ArtemisError


class Route:
    method: str
    path: str
    url: str

    BASE = "https://old.reddit.com"

    def __init__(self, method, path):
        self.method = method
        self.path = path
        self.url = self.BASE + self.path


class Reddit:
    def __init__(self, session: ClientSession):
        self.session: ClientSession = session

    @staticmethod
    def _gen_session_id() -> str:
        id_length = 16
        rand_max = 1 << (id_length * 4)
        return "%0.*x" % (id_length, random.randrange(rand_max))

    async def _request(self, route: Route, **kwargs) -> dict[str, Any]:
        headers = {"User-Agent": random_user_agent()}
        cookies = {
            "reddit_session": self._gen_session_id(),
            "_options": "%7B%22pref_quarantine_optin%22%3A%20true%7D",
        }
        async with self.session.request(
            route.method, route.url, headers=headers, cookies=cookies, **kwargs
        ) as r:
            data = await r.json()
            return data

    async def subreddit(
        self,
        name: str = "all",
        sort: Literal["hot", "new"] = "hot",
        include_stickied_and_pinned: bool = False,
    ) -> list[Post]:
        route = Route("GET", f"/r/{name}/{sort}.json")
        data = await self._request(route)

        if data.get("reason"):
            raise ArtemisError(f"This subreddit is inaccessible.\nReason: `{data['reason']}`")
        if not data.get("data") or not data["data"]["children"]:
            raise ArtemisError(f"Subreddit `{name}` not found.")

        posts = [Post(post["data"]) for post in data["data"]["children"]]

        if not include_stickied_and_pinned:
            posts = [post for post in posts if not post.stickied and not post.pinned]

        return posts

    async def post(self, pid: str):
        route = Route("GET", f"/{pid}.json?limit=1")
        try:
            data = await self._request(route)
            post_data = data[0]["data"]["children"][0]["data"]
            return Post(post_data)
        except Exception:
            return None

    async def random(self, subreddit: str = "all", *args, **kwargs) -> Post:
        posts = await self.subreddit(subreddit, *args, **kwargs)
        return random.choice(posts)

    async def random_image(self, subreddit: str = "all", *args, **kwargs) -> str:
        posts = await self.subreddit(subreddit, *args, **kwargs)
        images = [post for post in posts if post.image or post.gallery]
        post = random.choice(images)

        if post.gallery:
            return post.gallery[0]
        return post.image


class Post:
    ICON = "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"
    GOLD_ICON = "https://www.redditstatic.com/gold/awards/icon/gold_64.png"

    def __init__(self, data: dict):
        self.data = data

        self.title = html.unescape(self.data["title"])
        self.body = self.data.get("selftext")
        self.thumbnail = self.data.get("thumbnail", "")

        self.over_18 = self.data.get("over_18")
        self.stickied = self.data.get("stickied")
        self.pinned = self.data.get("pinned")
        self.spoiler = self.data.get("spoiler")
        self.score = self.data.get("score", "N/A")
        self.num_comments = self.data.get("num_comments", "N/A")
        self.gilded = self.data.get("gilded")
        self.awards = self.data.get("all_awardings")

        self.permalink = "https://reddit.com" + self.data.get("permalink", "")
        self.subreddit = self.data.get("subreddit")
        self.subreddit_prefixed = f"r/{self.subreddit}"
        self.created_at = pendulum.from_timestamp(self.data["created_utc"], "UTC")

    @cached_property
    def image(self) -> Optional[str]:
        image = self.data.get("url_overridden_by_dest", "")

        if not self.body:
            if self.data.get("secure_media") or self.data.get("media_embed"):
                return None
            if re.search(r"(i\.redd\.it\/[^\/]+\.gifv)|gifv|webm", image):
                return None
            elif re.search(r"jpg|png|webp|gif|jfif|jpeg|imgur", image):
                return image
        return None

    @cached_property
    def video(self) -> Optional[str]:
        media = self.data.get("media") or self.data.get("secure_media")
        if not media:
            return None
        reddit_video = media.get("reddit_video")
        if not reddit_video:
            return None
        playlist = reddit_video.get("dash_url") or reddit_video.get("hls_url")
        if not playlist:
            return None
        return playlist

    @cached_property
    def preview(self) -> Optional[str]:
        try:
            preview = self.data["preview"]["images"][0]["source"]["url"]
            return html.unescape(preview)
        except Exception:
            return None

    @cached_property
    def gallery(self) -> list[str]:
        if not self.data.get("gallery_data") or not self.data.get("media_metadata"):
            return []

        images: list[str] = []
        metadata = self.data["media_metadata"]

        for image in self.data["gallery_data"]["items"]:
            media_id = image["media_id"]
            try:
                url = html.unescape(metadata[media_id]["s"]["u"])
            except Exception:
                url = html.unescape(metadata[media_id]["s"]["gif"])
            images.append(url)

        return images

    def get_warnings(self, nsfw: bool) -> str | None:
        warnings = []
        if self.spoiler:
            warnings.append("SPOILER")
        if nsfw:
            warnings.append("NSFW")
        if self.data.get("secure_media") or self.data.get("media_embed"):
            warnings.append("UNSUPPORTED MEDIA")

        if warnings:
            return f"`❗ {', '.join(warnings)}`"  # type: ignore
        return None

    def is_nsfw(self, message: discord.Message):
        return self.over_18 and message.guild and not message.channel.is_nsfw()

    async def to_embed(self, message: discord.Message) -> list[discord.Embed]:
        COLOUR = discord.Colour(0xFF4500)
        SPOILER_IMG_URL = "https://derpicdn.net/img/2016/5/22/1160541/medium.png"
        NSFW_IMG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/Znaczek_TV_-_dozwolone_od_lat_18.svg/150px-Znaczek_TV_-_dozwolone_od_lat_18.svg.png"

        files = []
        icon_url = None
        embed = discord.Embed(title=utils.trim(self.title, 256), url=self.permalink, colour=COLOUR)
        embeds = [embed]

        nsfw = self.is_nsfw(message)

        if self.image:
            embed.set_image(url=self.image)

        if self.body:
            body = html.unescape(utils.trim(self.body.strip(), 4096))
            images = re.findall(r"https.*(?:png|jpg|jpeg|webp|gif)\S*", body)
            for idx, url in enumerate(images[:10]):
                if idx == 0:
                    embed.set_image(url=url)
                else:
                    embeds.append(discord.Embed(color=COLOUR).set_image(url=url))

            if self.spoiler or nsfw:
                body = f"||{body}||"

            embed.description = body

        if self.gallery:
            for idx, url in enumerate(self.gallery[:10]):
                if idx == 0:
                    embed.set_image(url=url)
                else:
                    embeds.append(discord.Embed(colour=COLOUR).set_image(url=url))

        if not embed.image:
            if self.preview:
                embed.set_image(url=self.preview)
            elif self.thumbnail and "http" in self.thumbnail:
                embed.set_thumbnail(url=self.thumbnail)

        if nsfw:
            if embed.thumbnail:
                embed.set_thumbnail(url=NSFW_IMG_URL)
            elif embed.image:
                for idx, embed in enumerate(embeds):
                    embed.set_image(url=NSFW_IMG_URL)

        if self.spoiler:
            if embed.image and not files:
                for idx, embed in enumerate(embeds):
                    embed.set_image(url=SPOILER_IMG_URL)

        warnings = self.get_warnings(nsfw)
        if warnings:
            if embed.description:
                embed.description = f"{warnings}\n\n{embed.description}"
            else:
                embed.description = warnings

        if self.gilded:
            icon_url = self.GOLD_ICON
        elif self.awards:
            sorted_awards = sorted(self.awards, key=lambda x: int(x.get("count")), reverse=True)
            icon_url = sorted_awards[0]["icon_url"]

        upvotes = f"{intcomma(self.score)} upvote{'s' if self.score != 1 else ''}"
        comments = f"{intcomma(self.num_comments)} comment{'s' if self.num_comments != 1 else ''}"

        embed.set_author(
            name=self.subreddit_prefixed,
            icon_url=self.ICON,
            url=f"https://reddit.com/r/{self.subreddit}",
        )

        embeds[-1].set_footer(text=f"{upvotes} and {comments}", icon_url=icon_url)
        embeds[-1].timestamp = self.created_at

        return embeds
