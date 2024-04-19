from __future__ import annotations

import asyncio
import functools
import json
import re
import shlex
from dataclasses import dataclass
from io import BytesIO
from ipaddress import ip_address
from subprocess import PIPE
from time import perf_counter, time_ns
from time import time as _time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, Sequence, TypeVar
from urllib.parse import quote_plus, urlparse

import discord
import humanize
import pendulum
import pykakasi
import tomllib
from aiohttp.helpers import is_ip_address
from discord.ext import commands
import feedparser
from rapidfuzz import process

from .. import utils

if TYPE_CHECKING:
    from ..bot import Artemis


# url regex
URL_RE = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"


class ArtemisError(commands.CommandError):
    pass


class InvalidURL(ArtemisError):
    pass


class SSRFError(ArtemisError):
    pass


class CommandExecutionError(Exception):
    pass


class InvalidColour(commands.BadArgument):
    pass


class BetterColour(commands.Converter):
    async def convert(self, ctx, argument: str):
        colour_name = fuzzy_search_one(argument, list(utils.COMMON_COLOURS), cutoff=60)
        if not colour_name:
            raise InvalidColour("Invalid colour code/name.")
        argument = utils.COMMON_COLOURS[colour_name]
        colour = discord.Colour.from_str(argument)
        return colour


class URL(commands.Converter):
    """URL converter."""

    async def convert(self, ctx, argument: str):
        argument = argument.strip("<>")
        match = is_valid_url(argument)
        if match:
            check_for_ssrf(argument)
            return argument
        else:
            raise InvalidURL("That doesn't look like a valid URL.")


class Stopwatch:
    """A context manager to measure execution time."""

    def __enter__(self):
        self._t = perf_counter()
        return self

    def __exit__(self, type, value, tb):
        self._t = perf_counter() - self._t

    @property
    def result(self):
        return self._t

    @property
    def duration(self):
        return pendulum.duration(seconds=self._t)

    @property
    def humanized(self):
        return humanize.metric(self._t, "s")


class ProgressBarMessage:
    """Auto-updating progress bar using a discord message."""

    _total: int
    _current: int
    _msg: discord.Message | None
    _ctx: commands.Context[Artemis]
    _format: str
    _refresh_rate: int
    _prefix: str | None
    _bar_width: int
    _delete_on_finished = bool
    _finished = bool
    _finished_kwargs: dict

    def __init__(
        self,
        ctx: commands.Context[Artemis],
        total: int,
        prefix: str | None = None,
        format: str = "bytes",
        refresh_rate: int = 1,
        bar_width: int = 25,
        delete_on_finished: bool = False,
    ):
        self._ctx = ctx
        self._total = total
        self._prefix = prefix
        self._format = format
        self._refresh_rate = refresh_rate
        self._bar_width = bar_width
        self._msg = None
        self._current = 0
        self._finished_kwargs = {"content": "Done!"}
        self._finished = False
        self._delete_on_finished = delete_on_finished

    def _get_fmt(self):
        fmt = None

        if self._total == 0 and self._current == 0:
            return ""

        match self._format:
            case "bytes":
                fmt = humanize.naturalsize(self._current, binary=True)
            case "integer":
                fmt = self._current
            case "percent":
                fmt = ""
        return fmt

    async def _render(self):
        try:
            while not self._finished:
                print(vars(self))
                content = ""
                if self._prefix:
                    content += self._prefix + "\n"
                content += self._render_bar()

                if not self._msg:
                    self._msg = await self._ctx.send(content=content)
                else:
                    self._msg = await self._msg.edit(content=content)

                await asyncio.sleep(1 / self._refresh_rate)

            if self._msg:
                if self._delete_on_finished:
                    return await self._msg.delete()
                self._msg = await self._msg.edit(**self._finished_kwargs)
        except Exception as err:
            print(str(err))
            if self._msg:
                await self._msg.edit(content="Error while rendering progress bar.")

    def _render_bar(self):
        if self._total == 0:
            return f"??% `Unknown Size` {self._get_fmt()}"

        progress = self._current * self._bar_width // self._total

        bar = "["
        bar += "=" * (progress - 1) + ">"
        bar += " " * (self._bar_width - progress)
        bar += "]"

        percent = round(self._current / self._total * 100)
        return f"{percent}% `{bar}` {self._get_fmt()}"

    def start(self):
        asyncio.create_task(self._render())

    def set(self, val: int):
        self._current = val

    def set_total(self, val: int):
        self._total = val

    def set_prefix(self, prefix: str):
        self._prefix = prefix

    def increment(self, val: int):
        self._current += val

    def finish(self, **kwargs):
        self._finished = True
        if kwargs:
            self._finished_kwargs = kwargs

    def set_finished_kwargs(self, **kwargs):
        self._finished_kwargs = kwargs

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.finish()


def File(fp: bytes | str | list | dict, filename: str):
    """Dirty discord.File helper for fast debugging."""
    if isinstance(fp, bytes):
        buf = BytesIO(fp)
    elif isinstance(fp, str):
        buf = BytesIO(fp.encode("utf-8"))
    elif isinstance(fp, (list, dict)):
        buf = BytesIO(json.dumps(fp, indent=2, ensure_ascii=False).encode("utf-8"))
    else:
        raise TypeError("Invalid file pointer input.")

    buf.seek(0)
    return discord.File(buf, filename)


def read_text(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_json(path: str) -> Any:
    with open(path, "r") as f:
        return json.load(f)


def read_toml(path: str) -> Any:
    with open(path, "rb") as f:
        return tomllib.load(f)


def in_executor(func: Callable):
    """A decorator for running a function in a thread."""

    @functools.wraps(func)
    def decorator(*args: Any, **kwargs: Any):
        return asyncio.to_thread(func, *args, **kwargs)

    return decorator


def time(resolution: Literal["s", "ms", "ns"] = "s") -> int:
    """
    Return the current time in resolution since the unix epoch as an int.

    ### Parameters
    resolution: `Literal["s", "ms", "ns"]`
        Resolution of the returned time, seconds, milliseconds or nanoseconds.
    """
    match resolution:
        case "s":
            return int(_time())
        case "ms":
            return int(_time() * 1000)
        case "ns":
            return time_ns()


def trim(text: Optional[str], max: int) -> Optional[str]:
    """Trims text to specified max length."""
    if text is None:
        return None
    return f"{text[:max - 3]}..." if len(text) > max else text


def romajify(text: str, strict: bool = True) -> str:
    """
    Romajifies all Japanese characters.
    If strict, text containing any English characters won't be converted.
    """
    if strict and re.search(r"[a-zA-Z]", text):
        return text
    kana = pykakasi.kakasi().convert(text)
    romaji = "".join([group["hepburn"] + " " for group in kana])
    return romaji.strip()


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    if (
        not parsed.scheme
        or not parsed.netloc
        or not (parsed.scheme.startswith("http") and "." in parsed.netloc)
    ):
        return False
    return True


def check_for_ssrf(url: str):
    """Checks if the provided url contains private IP addresses."""
    hostname = urlparse(url).hostname
    if (
        hostname
        and hostname == "localhost"
        or is_ip_address(hostname)
        and ip_address(hostname).is_private
    ):
        raise SSRFError("Error: Invalid URL.")


def silence_url_embeds(message: str) -> str:
    """Silences link embeds in a message we send."""
    regex = re.compile(URL_RE)

    def repl(m):
        url = m.group(0)
        return f"<{url}>"

    ret = regex.sub(repl, str(message))
    return ret


def make_pages(data: List[Dict | Any], per_page: int = 5) -> List[List]:
    """Turn a list of items into pages."""
    pages = []
    while data:
        pages.append(data[:per_page])
        data = data[per_page:]
    return pages


def make_embeds(
    data: List[str | Dict],
    embed_base: discord.Embed,
    per_page: int = 5,
    etype: str = "description",
) -> list[discord.Embed]:
    """Turn a list of data into embed pages."""
    pages = make_pages(data, per_page=per_page)
    embeds = []

    if etype == "description":
        for page in pages:
            embed = embed_base.copy()
            embed.description = "\n".join(page)
            embeds.append(embed)
    elif etype == "fields":
        for page in pages:
            embed = embed_base.copy()
            for item in page:
                embed.add_field(name=item["name"], value=item["value"], inline=False)
            embeds.append(embed)
    return embeds


@dataclass
class CommandResult:
    stdout: bytes
    stderr: bytes
    returncode: Optional[int]

    @property
    def decoded(self) -> str:
        return self.stdout.decode() + self.stderr.decode()

    @property
    def ok(self) -> bool:
        return self.returncode == 0


async def run_cmd(args: str, shell=False, input=None) -> CommandResult:
    """Runs a shell command and returns raw/formatted output."""
    stdin = PIPE if input else None
    try:
        if shell:
            process = await asyncio.create_subprocess_shell(
                args, stdout=PIPE, stderr=PIPE, stdin=stdin
            )
        else:
            split_args = shlex.split(args)
            process = await asyncio.create_subprocess_exec(
                *split_args, stdout=PIPE, stderr=PIPE, stdin=stdin
            )

        stdout, stderr = await process.communicate(input=input)
    except Exception as err:
        raise CommandExecutionError(err)

    return CommandResult(stdout, stderr, process.returncode)


async def run_cmd_to_file(args: str, filename: str, shell=False) -> discord.File | str:
    """Runs a shell command and returns the output as a discord.File."""
    result = await run_cmd(args, shell=shell)
    stdout, stderr = result.stdout, result.stderr

    if not result.ok:
        raise CommandExecutionError(stderr.decode())

    fp = BytesIO(stdout)
    fp.seek(0)

    if len(stdout) <= 25 * 1024**2:
        return discord.File(fp, filename)
    else:
        raise CommandExecutionError("The file is too big to upload.")


def parse_short_time(time_string: str, as_duration: bool = False):
    compiled = re.compile(
        """(?:(?P<years>[0-9])(?:years?|y))?              # e.g. 2y
            (?:(?P<months>[0-9]{1,2})(?:months?|mo))?     # e.g. 2months
            (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?        # e.g. 10w
            (?:(?P<days>[0-9]{1,5})(?:days?|d))?          # e.g. 14d
            (?:(?P<hours>[0-9]{1,5})(?:hours?|h))?        # e.g. 12h
            (?:(?P<minutes>[0-9]{1,5})(?:minutes?|m))?    # e.g. 10m
            (?:(?P<seconds>[0-9]{1,5})(?:seconds?|s))?    # e.g. 15s
        """,
        re.VERBOSE,
    )

    match = compiled.fullmatch(time_string)
    if match is None or not match.group(0):
        raise commands.BadArgument("Invalid time provided.")

    data = {k: int(v) for k, v in match.groupdict(default=0).items()}
    if as_duration:
        return pendulum.duration(**data)
    return pendulum.now("UTC") + pendulum.duration(**data)


async def get_attachment_or_url(
    ctx: commands.Context[Artemis], message: discord.Message, url: Optional[str], types: list = None
) -> bytes:
    if not message.attachments and not url:
        raise ArtemisError("Please send me an attachment or URL first!")
    elif message.attachments:
        attachment = message.attachments[0]
        if types:
            if not attachment.content_type:
                raise ArtemisError("Cannot guess file content type.")
            elif attachment.content_type not in types:
                raise ArtemisError(
                    f"Unsupported file type, should be one of: `{', '.join(types)}`."
                )
        return await attachment.read()
    elif url:
        url = url.strip("<>")
        if not is_valid_url(url):
            raise ArtemisError("URL is not valid.")
        utils.check_for_ssrf(url)

        headers = {"User-Agent": ctx.bot.user_agent}
        try:
            async with ctx.bot.session.get(url, headers=headers) as r:
                if not r.ok:
                    raise ArtemisError(f"URL returned error status {r.status}")
                if types:
                    if not r.content_type:
                        if "discord" not in url:
                            raise ArtemisError("Cannot guess file content type.")
                    elif r.content_type not in types:
                        raise ArtemisError("Unsupported file type, should be an image.")
                return await r.read()
        except Exception:
            raise ArtemisError("An error occured when trying to connect to the given URL.")


async def get_message_or_reference(ctx: commands.Context[Artemis]) -> discord.Message:
    reference = ctx.message.reference
    if reference:
        try:
            return reference.cached_message or await ctx.channel.fetch_message(reference.message_id)
        except Exception:
            return ctx.message
    else:
        return ctx.message


T = TypeVar("T")


def fuzzy_search(
    query: str,
    choices: Sequence[T],
    key: str | None = None,
    cutoff: float | None = None,
    limit: int = 5,
) -> Sequence[T]:
    """Fuzzy search in a list of strings or a list of dictionaries, returns the matching entries."""
    if isinstance(choices[0], str):
        return [
            result[0]
            for result in process.extract(query.lower(), choices, score_cutoff=cutoff, limit=limit)
        ]

    if not key:
        raise KeyError("'key' is required for dictionary search")
    lookup = {entry[key]: entry for entry in choices}
    results = process.extract(query.lower(), lookup.keys(), score_cutoff=cutoff, limit=limit)
    return [lookup[result[0]] for result in results]


def fuzzy_search_one(
    query: str, choices: Sequence[T], key: str = None, cutoff: float = None
) -> Optional[T]:
    """Fuzzy search in a list of strings or a list of dictionaries, returns one matching entry."""
    return next(iter(fuzzy_search(query, choices, key=key, cutoff=cutoff, limit=1)), None)


@dataclass
class BingResult:
    url: str
    title: str
    description: str


async def search_bing(
    ctx: commands.Context[Artemis],
    query: str,
    site: str | None = None,
) -> list[BingResult]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_3) AppleWebKit/601.4.4 (KHTML, like Gecko) Vienna/3.0.0 Safari/1601.4.4"
    }
    if site:
        query = quote_plus(f"{query.strip()} {site}")

    url = f"https://www.bing.com/search?q={query}&setLang=en&format=rss"

    async with ctx.bot.session.get(url, headers=headers) as r:
        if not r.ok:
            raise ArtemisError(f"Bing returned {r.status} {r.reason}")
        rss = await r.text()

    feed = feedparser.parse(rss)
    entries = feed.entries

    return [BingResult(entry["link"], entry["title"], entry["summary"]) for entry in entries]
