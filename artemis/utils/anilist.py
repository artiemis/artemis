from __future__ import annotations

import re
from typing import Any, Optional

import discord
from anilist.types import Anime, Character, Manga

from .common import trim

ANILIST_COLOR = 0x02A9FF
FOOTER = "Powered by AniList APIv2"

media_formats_map = {
    "TV": "TV",
    "TV_SHORT": "TV Short",
    "MOVIE": "Movie",
    "SPECIAL": "Special",
    "OVA": "OVA",
    "ONA": "ONA",
    "MUSIC": "Music",
    "MANGA": "Manga",
    "NOVEL": "Novel",
    "ONE_SHOT": "One Shot",
}


class BaseEmbed(discord.Embed):
    def __init__(self, *args, **kwargs):
        super().__init__(color=ANILIST_COLOR, *args, **kwargs)
        self.set_footer(text=FOOTER)


def get(obj: Any, prop: str, default: Optional[str] = None):
    return getattr(obj, prop, default)


def get_character_summary(character: Character) -> Optional[str]:
    if not get(character, "description"):
        return "No description available."

    clean, spoilers = [], []
    description = character.description

    def repl(m):
        spoilers.append(f"||{m.group(1)}||")
        return ""

    description = re.sub(r"~!(.+?)!~", repl, description, re.S)

    lines = description.split("\n")
    lines = [line for line in lines if line]

    for line in lines:
        if re.search(r"^__.+(:__|__:|__.+:)|^\*\*.+(:\*\*|\*\*:|\*\*.+:)", line):
            continue
        else:
            clean.append(line.strip())

    if clean:
        ret = clean[0]
        if len(ret) < 100 and len(clean) > 1:
            ret += f"\n{clean[1]}"
        return trim(ret, 512)
    elif spoilers:
        return spoilers[0]
    else:
        return "No description available."


def build_anilist_embed(result: Anime | Manga) -> discord.Embed:
    title = get(result.title, "english", result.title.romaji)
    description = result.description.split("<br>")[0] if get(result, "description") else ""
    description = re.sub(r"<.+?>", "", description)

    source = result.source.replace("_", " ").title() if get(result, "source") else "N/A"
    status = result.status.replace("_", " ").title() if get(result, "status") else "N/A"
    start_date: Any = get(result, "start_date")
    url = result.url
    mid = result.id

    embed = BaseEmbed(title=title, url=url, description=description)
    embed.set_image(url=f"https://img.anili.st/media/{mid}")
    embed.add_field(name="Source", value=source)
    embed.add_field(name="Status", value=status)

    if start_date and get(start_date, "year"):
        embed.add_field(name="Release Year", value=start_date.year, inline=True)

    if isinstance(result, Anime):
        nextairing = get(result, "next_airing", None)
        episodes = get(result, "episodes") or get(nextairing, "episode")
        duration = get(result, "duration")

        media_format = media_formats_map.get(result.format)
        embed.add_field(name="Type", value=media_format)

        if episodes:
            embed.add_field(name="Episodes", value=episodes)
        if duration:
            duration = (
                str(duration) + " mins per ep." if media_format == "TV" else str(duration) + " mins"
            )
            embed.add_field(name="Duration", value=duration)
    elif isinstance(result, Manga):
        volumes = get(result, "volumes")
        chapters = get(result, "chapters")

        if volumes:
            embed.add_field(name="Volumes", value=volumes)
        if chapters:
            embed.add_field(name="Chapters", value=chapters)
    return embed


def build_character_embed(character: Character) -> discord.Embed:
    name = character.name.full
    if get(character.name, "native"):
        name += f" ({character.name.native})"
    url = character.url
    image = character.image.large if get(character, "image") else None
    media = character.media if get(character, "media") else None
    description = get_character_summary(character) or ""

    if media:
        media_joined = "**Featured in:**\n"
        for entry in media[:3]:
            title = entry["title"].get("english") or entry["title"].get("romaji")
            entry_url = f"https://anilist.co/{entry['type'].lower()}/{entry['id']}"
            media_joined += f"[{title}]({entry_url})\n"
        if len(media) > 3:
            media_joined += f"[**+ {len(media) - 3} more**]({url})"
        description += f"\n\n{media_joined}"

    embed = BaseEmbed(title=name, url=url, description=description)
    if image:
        embed.set_image(url=image)
    return embed
