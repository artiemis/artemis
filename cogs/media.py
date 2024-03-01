from __future__ import annotations, unicode_literals

import asyncio
import html
import re
import shlex
import struct
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus

import discord
import humanize
import pendulum
import yt_dlp
from bs4 import BeautifulSoup
from discord.ext import commands
from PIL import Image
from pycaption import SRTWriter, WebVTTReader
from yt_dlp.utils import parse_duration

import utils
from utils.common import ArtemisError
from utils.constants import MAX_DISCORD_SIZE, MAX_LITTERBOX_SIZE
from utils.catbox import CatboxError
from utils.flags import DLFlags
from utils.iso_639 import get_language_name
from utils.views import DropdownView

if TYPE_CHECKING:
    from bot import Artemis

TEMP_DIR = Path("data/temp/")
yt_dlp.utils.bug_reports_message = lambda: ""

DEFAULT_OPTS = {
    "quiet": True,
    "noprogress": True,
    "no_warnings": True,
    "socket_timeout": 5,
    "noplaylist": True,
    "playlistend": 1,
    "nopart": True,
}


def format_ytdlp_error(error: str) -> str:
    ret = utils.silence_url_embeds(error)
    ret = (
        ret.removeprefix("[generic] ")
        .removeprefix("None: ")
        .split("Set --default-search")[0]
        .split("(caused by")[0]
        .split("You might want to use a VPN")[0]
    )
    return ret


async def run_ytdlp(query: str, opts: dict, download: bool = True) -> dict:
    try:
        with yt_dlp.YoutubeDL(opts) as ytdl:
            return await asyncio.to_thread(ytdl.extract_info, query, download=download)
    except yt_dlp.utils.YoutubeDLError as error:
        raise ArtemisError(format_ytdlp_error(error))


class Media(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    @commands.command(aliases=["nf"])
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def netflix(self, ctx: commands.Context, *, query: str):
        """Check if and where a show is available on Netflix."""

        await ctx.typing()
        data = await self.bot.unogs.search(query)
        if "total" not in data:
            return await ctx.reply("The API returned no data, weird!")
        elif data["total"] == 0:
            return await ctx.reply("No results found.")
        elif data["total"] == 1:
            data = data["results"][0]
        else:
            view = DropdownView(
                ctx,
                data["results"],
                lambda x: html.unescape(x["title"]),
                placeholder="Choose title...",
            )
            data = await view.prompt()
            if not data:
                return

        title = html.unescape(data["title"])
        synopsis = html.unescape(data["synopsis"])
        nfid = data["nfid"]
        nfurl = f"https://www.netflix.com/title/{data['nfid']}"
        img = data.get("poster") or data.get("img")

        countries = await self.bot.unogs.fetch_details(nfid, "countries")
        flags = " ".join([f":flag_{country['cc'].strip().lower()}:" for country in countries])

        audio = []
        subtitles = []
        for country in countries:
            audio += country["audio"].split(",")
            subtitles += country["subtitle"].split(",")
        audio, subtitles = sorted(set(audio)), sorted(set(subtitles))
        audio, subtitles = [a for a in audio if a], [s for s in subtitles if s]

        embed = discord.Embed(title=title, description=synopsis, url=nfurl, color=0xE50914)
        if img and "http" in img:
            embed.set_image(url=img)
        embed.set_author(
            name="Netflix",
            icon_url="https://assets.nflxext.com/us/ffe/siteui/common/icons/nficon2016.png",
        )
        embed.add_field(name="Availability", value=flags)
        embed.add_field(name="Audio", value=", ".join(audio), inline=False)
        embed.add_field(name="Subtitles", value=", ".join(subtitles), inline=False)
        await ctx.reply(embed=embed)

    @commands.command(aliases=["thumb"])
    async def thumbnail(self, ctx: commands.Context, url: str):
        """Gives you a video thumbnail URL for a video from any site supported by YTDL."""
        url = url.strip("<>")
        utils.check_for_ssrf(url)

        await ctx.typing()

        youtube = re.search(
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]+)", url
        )
        if youtube:
            thumbnail = f"https://i.ytimg.com/vi/{youtube.group(1)}/maxresdefault.jpg"
        else:
            info_dict = await run_ytdlp(url, DEFAULT_OPTS, download=False)

            thumbnail = info_dict.get("thumbnail")
            if not thumbnail:
                return await ctx.reply("No thumbnail available.")

        await ctx.reply(thumbnail)

    @commands.command(aliases=["audio"])
    @commands.max_concurrency(1)
    async def dlaudio(self, ctx: commands.Context, url: str, fmt: Optional[str]):
        """
        Downloads audio from a YouTube video in original format or mp3.
        To convert the audio to mp3, pass 'mp3' after the URL.
        """
        url = url.strip("<>")
        utils.check_for_ssrf(url)
        ytdl_opts = {
            **DEFAULT_OPTS,
            "format": "251/140/ba",
            "outtmpl": TEMP_DIR.joinpath("%(id)s.%(ext)s").as_posix(),
            "match_filter": yt_dlp.match_filter_func("duration < 1500"),
        }

        if fmt == "mp3":
            ytdl_opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
            ]

        async with ctx.typing():
            info_dict = await run_ytdlp(url, ytdl_opts)

            title = utils.romajify(info_dict.get("title"))
            vid_id = info_dict.get("id")
            ext = info_dict.get("ext") if fmt != "mp3" else "mp3"
            filename = f"{vid_id}.{ext}"
            pretty_filename = f"{title}.{ext}" if ext != "webm" else f"{title}.ogg"
            path = TEMP_DIR / filename

            if not path.exists():
                return await ctx.reply("ERROR: The file is too big for me to upload!")

            await ctx.reply(file=discord.File(path, pretty_filename))
            path.unlink()

    @commands.command(usage="<url> <lang>", aliases=["subs", "subtitles"])
    async def dlsubs(self, ctx: commands.Context, url: str, lang: Optional[str]):
        """
        Downloads a subtitle file from any site supported by YTDL.
        Makes you choose the language if more than one detected and no `<lang>` given.
        `<lang>` is optional if the video only has one subtitle file.
        Pass `all` to `<lang>` to get all of the subtitles.
        """
        url = url.strip("<>")
        utils.check_for_ssrf(url)
        ytdl_opts = {
            **DEFAULT_OPTS,
            "writesubtitles": True,
            "subtitleslangs": ["all"],
        }

        async def process_one(data: dict) -> discord.File:
            url = data.get("url")
            ext = data["ext"]
            if data.get("data") is not None:
                sub_data = data["data"]
            else:
                async with self.bot.session.get(url) as r:
                    sub_data = await r.text()
            if ext == "vtt":
                try:
                    sub_data = str(SRTWriter().write(WebVTTReader().read(sub_data)))
                    ext = "srt"
                except Exception:
                    pass
            filename = f"{yt_dlp.utils.sanitize_filename(title)}-{data['lang']}.{ext}"
            return discord.File(BytesIO(sub_data.encode("utf-8")), filename)

        async def process(data: list[dict], lang: str = None) -> discord.File:
            if lang:
                found = discord.utils.find(lambda x: x["lang"] == lang)
                if not data:
                    raise ArtemisError("No subtitles available for that language.")
                return await process_one(found)
            elif len(data) == 1:
                return await process_one(data[0])

            zip_buffer = BytesIO()

            coros = [process_one(entry) for entry in data]
            files: list[discord.File] = await asyncio.gather(*coros)

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
                for file in files:
                    zip_file.writestr(file.filename, file.fp.read())
            zip_buffer.seek(0)

            filename = f"{title}-subs.zip"
            return discord.File(zip_buffer, filename)

        async with ctx.typing():
            info_dict = await run_ytdlp(url, ytdl_opts, download=False)

        title = utils.romajify(info_dict.get("title")).replace(" ", "_")
        subtitles: dict = info_dict.get("requested_subtitles")

        if not subtitles:
            return await ctx.reply("No subtitles available.")

        file = None
        subtitles = [{"lang": k, **v} for k, v in subtitles.items()]

        if lang:
            if lang == "all":
                file = await process(subtitles)
            else:
                try:
                    file = await process(subtitles, lang)
                except KeyError:
                    return await ctx.reply("No subtitles available for that language.")
        elif len(subtitles) == 1:
            file = await process(subtitles)
        elif len(subtitles) > 1:
            view = DropdownView(
                ctx,
                subtitles,
                lambda item: item["lang"],
                lambda item: item.get("name") or get_language_name(item["lang"].lower()) or None,
                "Choose one or more...",
                25,
                True,
            )
            view.message = await ctx.reply("Which language(s)?", view=view)
            if await view.wait():
                return await view.message.edit(content="You took too long!", view=None)

            result = view.result
            async with ctx.typing():
                file = await process(result)

        await ctx.reply(file=file)

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def mediainfo(self, ctx: commands.Context, url: str, format: Optional[str]):
        """Returns MediaInfo output for a media file."""

        url = url.strip("<>")
        utils.check_for_ssrf(url)
        if not format:
            format = (
                "bv/best"
                if any([domain in url for domain in ("youtube", "youtu.be")])
                else "b/mp4/b*"
            )
        ytdl_opts = {**DEFAULT_OPTS, "format": format}

        async with ctx.typing():
            info_dict = await run_ytdlp(url, ytdl_opts, download=False)

            title = info_dict.get("title")
            url = info_dict["url"]
            result = await utils.run_cmd(f'mediainfo "{url}"')

            if not result.ok:
                return await ctx.reply(result.decoded)

            lines = result.decoded.split("\n")
            lines.pop(1)
            output = "\n".join(lines)

            data = BytesIO(output.encode())
            fp = discord.File(data, f"{utils.romajify(title)}.txt")
        await ctx.reply(f"Media information for `{title}`", file=fp)

    @commands.command(aliases=["screenshot", "ss"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def screencap(self, ctx: commands.Context, url: str, timestamp: Optional[str] = "1"):
        """
        Takes a video screencap at a specified timestamp.

        Valid timestamp formats:
        - `SS` or `SS.ms`
        - `HH:MM:SS` or `HH:MM:SS.ms`
        """
        TIMESTAMP_RE = r"\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?"
        SECONDS_RE = r"\d{1,5}(?:\.\d{1,3})?"
        url = url.strip("<>")
        utils.check_for_ssrf(url)
        ytdl_opts = {**DEFAULT_OPTS, "format": "bv*/b"}

        @utils.in_executor
        def to_jpeg(image):
            im = Image.open(image)
            buff = BytesIO()
            im.save(buff, "JPEG", quality=90)
            buff.seek(0)
            return buff

        if not (re.fullmatch(TIMESTAMP_RE, timestamp) or re.fullmatch(SECONDS_RE, timestamp)):
            return await ctx.reply("Invalid timestamp format, check out `$help screencap`.")

        async with ctx.typing():
            info_dict = await run_ytdlp(url, ytdl_opts, download=False)

            title = info_dict["title"]
            url = info_dict["url"]

            if info_dict.get("is_live"):
                args = f'ffmpeg -hide_banner -loglevel warning -i "{url}" -vframes 1 -c:v png -f image2 -'
            else:
                args = f'ffmpeg -hide_banner -loglevel warning -ss {timestamp} -i "{url}" -vframes 1 -c:v png -f image2 -'

            result = await utils.run_cmd(args)
            stdout, stderr = result.stdout, result.stderr
            if not result.ok:
                return await ctx.reply(stderr.decode().split("pipe:")[0])

            w, h = struct.unpack(">II", stdout[16:20] + stdout[20:24])
            msg = f"Resolution: {w}x{h}"
            buff = BytesIO(stdout)

            if len(stdout) > MAX_DISCORD_SIZE:
                buff = await to_jpeg(buff)
                msg += "\nThe image was too big for me to upload so I converted it to JPEG Q90."
            dfile = discord.File(buff, f"{title}.png")
        return await ctx.reply(content=msg, file=dfile)

    @commands.command(usage="[format:] [trim:] <url>", aliases=["dl"])
    @commands.max_concurrency(1)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def download(self, ctx: commands.Context, *, flags: DLFlags):
        """
        Downloads videos from websites supported by youtube-dl.

        The download fails if the video is more than 1 hour long or its filesize exceeds 1 GB.
        Only one command can run at once and every user has a 30 second cooldown.

        Optional flags:
        `format` or `f` - youtube-dl format choice (only when trim flag is not present)
        `trim` or `t` - Trim selection of the form `start-end`.

        Valid trim selection formats:
        - `SS-SS` or `SS.ms-SS.ms`
        - `MM:SS-MM:SS` or `MM:SS.ms-MM:SS.ms`
        - `HH:MM:SS-HH:MM:SS` or `HH:MM:SS.ms-HH:MM:SS.ms`

        Examples:
        `{prefix}download https://youtu.be/dQw4w9WgXcQ`
        `{prefix}download f:22 https://youtu.be/o6wtDPVkKqI`
        `{prefix}dl trim:41-58 https://youtu.be/uKxyLmbOc0Q`
        `{prefix}dl t:01:15-01:27 https://youtu.be/qUk1ZoCGqsA`
        `{prefix}dl t:120-160 https://www.reddit.com/r/anime/comments/f86otf/`
        """
        path: Path = None
        msg: discord.Message = None
        finished = False
        state = "downloading"
        template = TEMP_DIR.joinpath("%(id)s.%(ext)s").as_posix()

        url = flags.url
        format = flags.format
        trim = flags.trim
        ss, to = flags.ss, None

        async def monitor_download():
            nonlocal msg, state
            path = Path("./data/temp/")
            while not finished:
                content = "Processing..."
                if state == "downloading":
                    match = None
                    files = list(path.iterdir())
                    if files:
                        match = max(files, key=lambda f: f.stat().st_size)
                    if match:
                        size = match.stat().st_size
                        size = humanize.naturalsize(size, binary=True)
                        content = f":arrow_down: `Downloading...` {size}"
                    else:
                        content = ":arrow_down: `Downloading...`"
                elif state == "uploading":
                    content = ":arrow_up: `Uploading...`"

                if not msg:
                    msg = await ctx.reply(content)
                else:
                    msg = await msg.edit(content=content)
                await asyncio.sleep(1)
            if msg:
                await msg.delete()

        try:
            url = url.strip("<>")
            utils.check_for_ssrf(url)
            if not url:
                raise ArtemisError("No URL provided.")

            def match_filter(info_dict, incomplete):
                nonlocal url
                if "#_sudo" in url and ctx.author.id == self.bot.owner_id:
                    return None
                duration = info_dict.get("duration")
                filesize = info_dict.get("filesize") or info_dict.get("filesize_approx")
                is_live = info_dict.get("is_live")
                if is_live:
                    raise ArtemisError("Streams are not supported.")
                elif trim:
                    return None
                elif not duration and not filesize:
                    raise ArtemisError("Failed to extract duration and filesize.")
                elif filesize and (filesize < 1 or filesize > MAX_LITTERBOX_SIZE):
                    raise ArtemisError("The video is too big (> 1 GB).")
                elif duration and (duration < 0 or duration > 3600):
                    raise ArtemisError("The video is too long (> 1 hour).")
                else:
                    return None

            ytdl_opts = {**DEFAULT_OPTS, "outtmpl": template, "match_filter": match_filter}

            if "youtube.com" in url or "youtu.be" in url:
                ytdl_opts["format"] = "248+251/247+251/137+140/136+140/bv*+ba/b"
            else:
                ytdl_opts["format_sort"] = ["ext", "+vcodec:avc"]

            if trim:
                dur = tuple(map(parse_duration, trim.strip().split("-")))
                if len(dur) == 2 and all(t is not None for t in dur):
                    ss, to = dur
                else:
                    raise ArtemisError("Invalid trim selection. Must be of the form `start-end`.")

                args = {
                    "ffmpeg": shlex.split("-hide_banner -loglevel error"),
                    "ffmpeg_i": shlex.split(f"-ss {ss} -to {to}"),
                }
                ytdl_opts["format"] = f"({ytdl_opts['format']})[protocol!*=dash][protocol!*=m3u8]"
                ytdl_opts["external_downloader"] = {"default": "ffmpeg"}
                ytdl_opts["external_downloader_args"] = args

                diff = to - ss
                if diff > 3600:
                    raise ArtemisError("The trim selection is too long (> 1 hour).")
                elif diff < 1:
                    raise ArtemisError("The trim selection cannot be negative or zero.")
            if format:
                if trim:
                    raise ArtemisError("Format choice is not supported with a trim selection.")
                ytdl_opts["format"] = format

            info_dict = None
            asyncio.create_task(monitor_download())
            async with ctx.typing():
                info_dict = await run_ytdlp(url, ytdl_opts)
            state = "uploading"

            title = utils.romajify(info_dict.get("title"))
            vid_id = info_dict.get("id")
            ext = info_dict.get("ext")
            filename = f"{vid_id}.{ext}"
            if trim:
                discord_filename = f"{title}_{round(ss)}-{round(to)}.{ext}"
            else:
                discord_filename = f"{title}.{ext}"

            path = TEMP_DIR / filename
            if not path.exists():
                raise ArtemisError(f"Internal Error: File {path} does not exist.")
            size = path.stat().st_size

            async with ctx.typing():
                if size <= utils.MAX_DISCORD_SIZE:
                    await ctx.reply(file=discord.File(path, discord_filename))
                elif size <= MAX_LITTERBOX_SIZE:
                    try:
                        res = await self.bot.litterbox.upload(path.as_posix(), 24)
                        expiration = discord.utils.format_dt(pendulum.now("UTC").add(hours=24))
                        await ctx.reply(f"This file will expire on {expiration}\n{res}")
                    except CatboxError as err:
                        await ctx.reply(err)
                else:
                    raise ArtemisError(
                        "The file passed the initial filesize guesstimation but is still too big to upload (> 1 GB)."
                    )
        except ArtemisError as err:
            ctx.command.reset_cooldown(ctx)
            if "requested format not available" in str(err) and ss and to:
                raise ArtemisError("Segmented streams are not supported with a trim selection.")
            raise err
        except Exception as err:
            raise err
        finally:
            finished = True
            if path and path.exists():
                path.unlink()

    @commands.command()
    @commands.cooldown(1, 1, commands.BucketType.default)
    async def dislikes(self, ctx: commands.Context, url: str):
        """Shows some statistics for a YouTube video including dislikes using Return YouTube Dislikes API."""
        YT_RE = r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]+)"

        if len(url) == 11:
            vid = url
        else:
            m = re.search(YT_RE, url)
            if not m:
                raise ArtemisError("Invalid YouTube URL or ID.")
            vid = m.group(1)

        params = {"videoId": vid}

        async with ctx.typing():
            async with self.bot.session.get(
                "https://returnyoutubedislikeapi.com/votes", params=params
            ) as r:
                if not r.ok:
                    if r.status == 404:
                        raise ArtemisError("Video not found.")
                    elif r.status == 400:
                        raise ArtemisError("Invalid video ID.")
                    else:
                        raise ArtemisError(
                            f"Return YouTube Dislikes API returned {r.status} {r.reason}"
                        )
                data = await r.json()

        views = humanize.intcomma(data["viewCount"])
        likes = humanize.intcomma(data["likes"])
        dislikes = humanize.intcomma(data["dislikes"])

        msg = f"**{views}** views\n**{likes}** likes\n**{dislikes}** dislikes"
        await ctx.reply(msg)

    @commands.command(aliases=["lg"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def libgen(self, ctx: commands.Context, *, query: str):
        """
        Search and download content from Library Genesis.
        Current mirror: libgen.is
        """
        LIBGEN_SEARCH_URL = "https://libgen.is/search.php?req={query}&column=def"

        if len(query) < 3:
            return await ctx.reply("The search query most contain at least 3 characters.")

        await ctx.typing()

        query = quote_plus(query)
        headers = {"User-Agent": self.bot.user_agent}

        async with self.bot.session.get(
            LIBGEN_SEARCH_URL.format(query=query), headers=headers
        ) as r:
            html = await r.text()
        soup = BeautifulSoup(html, "lxml")

        for el in soup.select("i"):
            el.decompose()

        table = soup.select(".c > tr")
        if not table:
            return await ctx.reply(
                "edge case hit, debug dump:\n",
                file=discord.File(BytesIO(html.encode("utf-8")), "search.html"),
            )
        elif len(table) == 1:
            return await ctx.reply("No results found.")

        entries = []
        for row in table[1:]:
            cells = row.select("td")
            title = ", ".join([s for s in cells[2].stripped_strings if s])
            year = cells[4].text
            if year:
                title += f" ({year})"
            author = cells[1].text
            mirrors = [cell.a["href"] for cell in cells[9:11]]
            ext = cells[8].text
            entries.append((title, author, mirrors, ext))

        if len(entries) == 1:
            result = entries[0]
        else:
            view = DropdownView(ctx, entries, lambda x: x[0], lambda x: x[1])
            result = await view.prompt("Which entry?")
            if not result:
                return

        async with ctx.typing():
            for mirror in result[2]:
                try:
                    async with self.bot.session.get(mirror, headers=headers) as r:
                        html = await r.text()
                except Exception:
                    continue

                soup = BeautifulSoup(html, "lxml")
                url = soup.find("a", text="GET")["href"]
                if not url:
                    continue

                try:
                    async with self.bot.session.get(url, headers=headers) as r:
                        filesize = r.headers.get("content-length")
                        disposition = r.content_disposition
                        if disposition:
                            filename = disposition.filename
                        else:
                            filename = f"{result[0]}.{result[3]}"

                        content = None
                        if not filesize:
                            content = await r.read()
                            filesize = len(content)

                        if int(filesize) > MAX_DISCORD_SIZE:
                            msg = "The file is too big to upload, so here's the link:"
                            desc = f"[{filename}]({url})"
                            embed = discord.Embed(description=desc, color=0xFEFEFE)
                            return await ctx.reply(msg, embed=embed)

                        if not content:
                            content = await r.read()

                        file = discord.File(BytesIO(content), filename)
                        return await ctx.reply(file=file)
                except Exception:
                    continue

            return await ctx.reply("Kernel panic: Could not contact any of the download mirrors.")


async def setup(bot: Artemis):
    await bot.add_cog(Media(bot))
