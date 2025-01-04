from __future__ import annotations

import json
import re
import unicodedata
from io import BytesIO, StringIO
from math import ceil, log2
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote, urlencode

import aiohttp
import discord
import pendulum
from aiocache import cached
from bs4 import BeautifulSoup
from colorama import Fore, Style
from discord.ext import commands
from discord.utils import format_dt
from humanize import intcomma
from PIL import Image

from .. import utils
from ..utils import enigma2
from ..utils.common import ArtemisError
from ..utils.flags import WikipediaFlags
from ..utils.views import DropdownView

if TYPE_CHECKING:
    from ..bot import Artemis


class Useful(commands.Cog):
    def __init__(self, bot: Artemis):
        self.bot: Artemis = bot

    @commands.command(aliases=["char"])
    async def charinfo(self, ctx: commands.Context, *, characters: str):
        """Shows you information about a number of characters using unicode data lookup."""
        length = len(characters)
        footer = f"{length} character{'s' if length != 1 else ''}"

        def to_string(c):
            digit = f"{ord(c):x}".upper()
            name = unicodedata.name(c, "Name not found.")
            return f"`{c}` - `U+{digit:>04}` - **[{name}](http://www.fileformat.info/info/unicode/char/{digit})**"

        desc = "\n".join(map(to_string, characters))
        if len(desc) > 4096:
            return await ctx.reply("Output too long to display.")
        await ctx.reply(
            embed=discord.Embed(
                title="Character Information",
                description=desc,
                colour=self.bot.pink,
                timestamp=pendulum.now("UTC"),
            ).set_footer(text=footer)
        )

    @commands.command(aliases=["redir"])
    async def redirect(self, ctx: commands.Context, url: utils.URL):
        """Checks if the given URL is a redirect and shows where it points to."""
        headers = {"User-Agent": self.bot.user_agent}
        js_redirects = r"location\.(?:replace|assign)\([\"\'](.+)[\"\']\)|location\.href\s?=\s?[\"\'](.+)[\"\']"
        redirect_url = None

        await ctx.typing()

        async def check_for_redirects(url, is_js_redirect=False):
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with self.bot.session.get(url, timeout=timeout, headers=headers) as r:
                    if "text/html" in r.content_type:
                        html = await r.text()
                        js_redirect = re.search(js_redirects, html)
                        if js_redirect:
                            redirect_url = js_redirect[1] or js_redirect[2]
                            return await check_for_redirects(redirect_url, is_js_redirect=True)

                    if r.history or not r.history and is_js_redirect:
                        return str(r.url), r.status, r.reason, r.content_type
                    else:
                        return None, None, None, None
            except Exception as err:
                print(err)
                raise ArtemisError("Oops, I couldn't connect to the given URL.")

        redirect_url, status, reason, content_type = await check_for_redirects(url)

        embed = discord.Embed(title="Redirect Check", color=self.bot.pink)
        embed.add_field(name="Input", value=url)

        if redirect_url:
            embed.add_field(name="Redirect", value=redirect_url, inline=False)
            embed.set_footer(text=f"Redirect HTTP Response: {status} {reason} • {content_type}")
        else:
            embed.add_field(name="Redirect", value="No redirects detected.", inline=False)
        await ctx.reply(embed=embed)

    @commands.command(aliases=["cur", "money", "cash"])
    async def currency(self, ctx: commands.Context, amount: str, cur_from: str, cur_to: str):
        """
        Convert currencies.
        Example usage: `{prefix}money 10 USD EUR`
        """
        cur_from = cur_from.upper()
        cur_to = cur_to.upper()
        currencies = ", ".join(utils.SUPPORTED_CURRENCIES)

        if not re.match(r"\d*(?:\.?|\,?)\d*$", amount):
            return await ctx.reply("Invalid amount.")
        elif cur_from not in currencies or cur_to not in currencies:
            return await ctx.reply(
                embed=discord.Embed(
                    title="Invalid or unsupported currency.",
                    description=f"Supported currencies:\n{self.bot.codeblock(currencies, '')}",
                    color=discord.Colour.red(),
                )
            )

        embed = discord.Embed(color=self.bot.pink)
        amount = amount.replace(",", ".")

        if cur_from == cur_to:
            desc = f"{intcomma(amount)} {Fore.BLUE}{cur_from}{Style.RESET_ALL} = {intcomma(amount)} {Fore.BLUE}{cur_to}"
            embed.description = self.bot.codeblock(desc, "ansi")
            return await ctx.reply(embed=embed)

        try:
            params = {"amount": amount, "from": cur_from, "to": cur_to}
            async with self.bot.session.get(
                "https://api.frankfurter.app/latest", params=params
            ) as r:
                json = await r.json()
            result = round(json["rates"][cur_to], 2)

            desc = f"{intcomma(amount)} {Fore.BLUE}{cur_from}{Style.RESET_ALL} = {intcomma(result)} {Fore.BLUE}{cur_to}"
            embed.description = self.bot.codeblock(desc, "ansi")
            await ctx.reply(embed=embed)
        except Exception:
            await ctx.reply("API Error: Failed to fetch conversions.")

    @commands.command(aliases=["colour"])
    async def color(self, ctx: commands.Context, *, colour: utils.BetterColour):
        """
        Look up a colour by its Hex value or Crayola name.

        Valid lookup formats:
        `#fff`
        `#ffffff`
        `rgb(0, 0, 0)`
        `blue`
        `magenta`
        """

        @utils.in_executor
        def make_solid_colour(colour, as_hex):
            buff = BytesIO()
            im = Image.new("RGB", (250, 250), colour)
            im.save(buff, "png")
            buff.seek(0)
            ret = discord.File(buff, f"{as_hex}.png")
            return ret

        rgb = colour.to_rgb()
        as_hex_raw = hex(colour.value)
        as_hex = "#" + as_hex_raw[2:]
        image = await make_solid_colour(rgb, as_hex_raw)

        if rgb == (255, 255, 255):
            colour = discord.Colour.from_rgb(254, 254, 254)

        embed = discord.Embed(color=colour)
        embed.set_thumbnail(url=f"attachment://{as_hex_raw}.png")
        embed.add_field(name="Hex", value=f"{as_hex.upper()}", inline=False)
        embed.add_field(name="RGB", value=rgb, inline=False)
        await ctx.reply(embed=embed, file=image)

    @commands.command(aliases=["clock"])
    async def time(self, ctx: commands.Context, tz: Optional[str]):
        """Check the time in given time zone or UTC."""
        if not tz:
            time = pendulum.now(tz="UTC")
        else:
            try:
                tz = utils.COMMON_TIMEZONES[tz.lower()]
            except Exception:
                pass
            tz = utils.fuzzy_search_one(tz, pendulum.timezones, cutoff=80)
            if tz:
                time = pendulum.now(tz=tz)
            else:
                return await ctx.reply(
                    embed=discord.Embed(
                        title="Invalid time zone",
                        description="[List of valid time zones](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568)",
                        colour=discord.Colour.red(),
                    )
                )
        await ctx.reply(
            embed=discord.Embed(
                title=f"Time for {time.timezone.name}",
                description=time.format("dddd[, ]HH:mm"),
                colour=self.bot.pink,
            )
        )

    @commands.command(aliases=["timezone", "tz"])
    async def convtime(self, ctx: commands.Context, time: str, from_tz: str, *to_tz):
        """
        Converts a datetime or time in given time zone to a different time zone or time zones.
        Accepts multiple time zones to convert to.

        One of the output time conversions will always be your local system time in a Discord Timestamp.

        Valid examples:
        `{prefix}tz 12:00 UTC`
        `{prefix}tz 14:00 CET ET`
        `{prefix}tz 15:33 tokyo egypt warsaw`
        `{prefix}tz "2022-01-01 22:00" UTC MSK PT WIT`
        """
        to_tzs = []

        try:
            from_tz = utils.COMMON_TIMEZONES[from_tz.lower()]
        except Exception:
            pass

        from_tz = utils.fuzzy_search_one(from_tz, pendulum.timezones)

        try:
            parsed_dt = pendulum.parse(time, tz=from_tz)
        except Exception:
            raise ArtemisError("Unable to parse the given time string.")

        for tz in to_tz:
            try:
                tz = utils.COMMON_TIMEZONES[tz.lower()]
            except Exception:
                pass
            curr_to_tz = utils.fuzzy_search_one(tz, pendulum.timezones)
            to_tzs.append(curr_to_tz)

        embed = discord.Embed(title="Time Zone Converter", colour=self.bot.pink)
        embed.add_field(name=from_tz, value=parsed_dt.format("dddd[, ]HH:mm"))

        for tz in to_tzs:
            converted_dt = parsed_dt.in_tz(tz)
            embed.add_field(name=tz, value=converted_dt.format("dddd[, ]HH:mm"), inline=False)

        if len(embed.fields) > 20:
            raise ArtemisError("Woah there! That's too many time zones.")

        if not to_tz:
            parsed_dt_utc = parsed_dt.in_tz("UTC")
            embed.add_field(name="Local time", value=format_dt(parsed_dt_utc, "t"), inline=False)
        await ctx.reply(embed=embed)

    @commands.command(aliases=["wiki"], usage="[lang:en] [l:en] <query>")
    async def wikipedia(self, ctx: commands.Context, *, flags: Optional[WikipediaFlags]):
        """
        Search the Wikipedias.
        If query is missing, shows a random article.

        Optional flags:
        `lang` or `l` - Wikipedia language subdomain (two-letter code).
        Defaults to English (`en`).
        """
        favicon = "https://en.wikipedia.org/static/apple-touch/wikipedia.png"

        if flags:
            query = flags.query
            endpoint = flags.lang or "en"
        else:
            query = None
            endpoint = "en"

        if endpoint == "jp":
            endpoint = "ja"

        API_BASE = f"https://{endpoint}.wikipedia.org/w/api.php"
        WEB_BASE = f"https://{endpoint}.wikipedia.org/wiki/"
        SEARCH = API_BASE + "?action=opensearch&format=json&redirects=resolve&search={}"
        EXTRACT = (
            API_BASE
            + "?action=query&format=json&prop=extracts|pageimages&exintro&explaintext&exsentences=5&piprop=original&redirects=1&titles={}"
        )
        RANDOM = API_BASE + "?action=query&format=json&redirects=1&list=random&rnnamespace=0"
        HEADERS = {"User-Agent": self.bot.real_user_agent}

        await ctx.typing()

        try:
            if query:
                async with self.bot.session.get(SEARCH.format(quote(query)), headers=HEADERS) as r:
                    data = await r.json()

                titles = data[1]
                if not titles:
                    return await ctx.reply("No results found.")
                elif len(titles) == 1:
                    title = titles[0]
                else:
                    view = DropdownView(ctx, titles, lambda x: x)
                    result = await view.prompt("Which page?")
                    if not result:
                        return
                    title = result
            else:
                async with self.bot.session.get(RANDOM, headers=HEADERS) as r:
                    data = await r.json()

                page = data["query"]["random"][0]
                title = page["title"]

            async with self.bot.session.get(EXTRACT.format(quote(title)), headers=HEADERS) as r:
                data = await r.json()

            pages = data["query"]["pages"]
            if not pages:
                return await ctx.reply("Title mismatch, action=query returned no pages.")

            page = pages[list(pages)[0]]
            extract = page["extract"]
            page_url = WEB_BASE + quote(title)

            image = page.get("original")
            if image:
                image_url = image.get("source") or None
            else:
                image_url = None

            embed = discord.Embed(
                title=title, description=utils.trim(extract, 4096), url=page_url, colour=0xFEFEFE
            )
            embed.set_author(name="Wikipedia", icon_url=favicon)
            if image_url:
                embed.set_image(url=image_url)
            await ctx.reply(embed=embed)

        except aiohttp.client_exceptions.ClientConnectionError:
            await ctx.reply("API Error: Invalid language endpoint.")

    @commands.command(aliases=["wttr"])
    async def weather(self, ctx: commands.Context, *, location: str):
        """Check the weather for given city/region/country."""
        LOC_RE = re.compile(r"Location:\s*(.*?)\s*\[")

        await ctx.typing()

        url = f"https://wttr.in/{quote(location)}"
        async with self.bot.session.get(f"{url}?T") as r:
            if r.status == 404:
                return await ctx.reply("Location not found.")
            data = await r.text()

        if "Sorry" in data:
            return await ctx.reply(data.split("\n\n")[0])

        loc = LOC_RE.search(data).group(1)
        text = "\n".join(data.split("\n")[1:7])
        wrapped = self.bot.codeblock(text, "py")

        embed = discord.Embed(title=loc, description=wrapped, url=url, color=0x7494D7)
        await ctx.reply(embed=embed)

    @commands.command(aliases=["qrd"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def qrdecode(self, ctx: commands.Context, url: Optional[utils.URL]):
        """
        Decode a QR code from an image.
        Accepts a URL or an attachment.
        """
        if not ctx.message.attachments and not url:
            return await ctx.reply("Please send me a valid image with a QR code.")
        elif ctx.message.attachments:
            url = ctx.message.attachments[0].url

        endpoint = "http://api.qrserver.com/v1/read-qr-code"
        params = {"fileurl": url}

        async with ctx.typing():
            async with self.bot.session.get(endpoint, params=params) as r:
                json = await r.json()

        result = json[0]["symbol"][0]
        text = result["data"]
        error = result["error"]

        if error:
            if "could not find" in error:
                return await ctx.reply("Could not find/read a QR code.")
            else:
                return await ctx.reply(f"API ERROR: {error}")

        if len(text) > 2000:
            await ctx.reply(file=discord.File(StringIO(text), "decoded_QR_code.txt"))
        await ctx.reply(text)

    @commands.command(name="map", aliases=["maps"])
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def _map(self, ctx: commands.Context, *, query: str):
        """
        Return a static map for a given location.

        Examples:
        `{prefix}map statue of liberty`
        `{prefix}map cieszyn, stawowa`
        """
        GEOCODER_API = "https://nominatim.openstreetmap.org/search"
        HEADERS = {"User-Agent": self.bot.real_user_agent, "Accept-Language": "en-US"}
        STATIC_MAP_URL = (
            "https://tyler-demo.herokuapp.com/?lat={lat}&lon={lon}&width=800&height=600&zoom={zoom}"
        )

        results = await self.bot.cache.get(f"geocoder:{query}")
        if not results:
            await ctx.typing()
            params = {"q": query, "format": "jsonv2"}
            async with self.bot.session.get(GEOCODER_API, params=params, headers=HEADERS) as r:
                results = await r.json()
                await self.bot.cache.set(f"geocoder:{query}", results, ttl=60)

        if not results:
            raise ArtemisError("No results found.")
        elif len(results) == 1:
            result = results[0]
        else:
            view = DropdownView(
                ctx,
                results,
                lambda x: x.get("display_name") or "Unknown display name.",
                lambda x: f"{x['osm_type']} {x['osm_id']}",
                "Choose place...",
            )
            result = await view.prompt()
            if not result:
                return
            await ctx.typing()

        lat = result["lat"]
        lon = result["lon"]
        address = result["display_name"]
        osm_id = result["osm_id"]
        osm_type = result["osm_type"]
        bbox: list[float] = result["boundingbox"]

        lon_diff = abs(float(bbox[2]) - float(bbox[3]))
        lat_diff = abs(float(bbox[0]) - float(bbox[1]))
        zoom_lon = ceil(log2(360 * 2 / lon_diff))
        zoom_lat = ceil(log2(180 * 2 / lat_diff))
        zoom = max(zoom_lon, zoom_lat) - 1
        zoom = max(0, min(zoom, 19))

        url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"

        async with self.bot.session.get(STATIC_MAP_URL.format(lat=lat, lon=lon, zoom=zoom)) as r:
            data = await r.read()

        data = BytesIO(data)
        file = discord.File(data, f"{osm_id}.png")

        embed = discord.Embed(title=utils.trim(address, 256), url=url, color=0xFEFEFE)
        embed.set_image(url=f"attachment://{osm_id}.png")
        embed.set_footer(
            text="Data © OpenStreetMap contributors, ODbL 1.0. https://osm.org/copyright"
        )

        await ctx.reply(embed=embed, file=file)

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def reverse(self, ctx: commands.Context, *, url: Optional[utils.URL]):
        """
        Yandex Reverse Image Search.
        """
        headers = {"User-Agent": self.bot.user_agent}
        bad_link_msg = "Couldn't upload image. Try uploading a different one."

        await ctx.typing()

        if not ctx.message.attachments and not url:
            return await ctx.reply("Please send me a valid image first!")
        elif ctx.message.attachments:
            url = ctx.message.attachments[0].url

        async with self.bot.session.get(
            f"https://yandex.com/images/search?url={url}&rpt=imageview", headers=headers
        ) as r:
            if not r.ok:
                return await ctx.reply(f"Yandex API Error: {r.status} {r.reason}")
            html = await r.text()

        if bad_link_msg in html:
            return await ctx.reply(bad_link_msg)

        soup = BeautifulSoup(html, "lxml")

        preview_img = soup.select_one(".CbirPreview-Image")
        assert preview_img
        preview_img_url = preview_img["src"]

        embed = discord.Embed(title="Uploaded image", color=0xFDDE55, url=r.url)
        embed.set_thumbnail(url=preview_img_url)
        embed.set_author(
            name="Yandex",
            icon_url="https://yastatic.net/s3/web4static/_/v2/oxjfXL1EO-B5Arm80ZrL00p0al4.png",
        )

        tags = soup.select(".CbirTags a")
        if tags:
            tags_fmt = []
            for tag in tags:
                href = "https://yandex.com" + tag["href"]
                tags_fmt.append(f"[{tag.span.text}]({href})")
            embed.add_field(
                name="Image appears to contain", value=", ".join(tags_fmt), inline=False
            )

        sizes = soup.select(".CbirOtherSizes a")
        if sizes:
            sizes_fmt = []
            for size in sizes[:4]:
                sizes_fmt.append(f"[{size.span.text}]({size['href']})")
            embed.add_field(name="Other image sizes", value=", ".join(sizes_fmt), inline=False)

        results = soup.select(".CbirSites-ItemInfo")

        for result in results[:3]:
            a = result.select_one(".CbirSites-ItemTitle a")
            if not a:
                continue

            title = a.text
            url = a["href"]
            url = f"[{utils.trim(url.split('//', 1)[-1], 50)}]({url})"
            description = result.select_one(".CbirSites-ItemDescription").text
            description = description if "http" not in description else None

            value = f"{url}\n{description}" if description else url
            embed.add_field(
                name=utils.trim(title, 256), value=utils.trim(value, 1024), inline=False
            )

        await ctx.reply(embed=embed)

    @cached(ttl=6 * 60 * 60)
    async def get_lyngsat_cse_url(self):
        headers = {"User-Agent": self.bot.user_agent}

        async with self.bot.session.get(
            "https://cse.google.com/cse.js?cx=009961667831609082040:rhpc-bbbuim", headers=headers
        ) as r:
            data = await r.text()

        cse_token = re.search(r"\"cse_token\":\s*\"(.*?)\"", data)
        if not cse_token:
            raise ArtemisError("Invalid CSE data, missing `cse_token`.")

        cselibv = re.search(r"\"cselibVersion\":\s*\"(.*?)\"", data)
        if not cselibv:
            raise ArtemisError("Invalid CSE data, missing `cselibVersion`.")

        cse_token, cselibv = cse_token.group(1), cselibv.group(1)

        params = urlencode(
            {
                "rsz": "filtered_cse",
                "num": "10",
                "hl": "en",
                "source": "gcsc",
                "gss": ".com",
                "cselibv": cselibv,
                "cx": "009961667831609082040:rhpc-bbbuim",
                "safe": "off",
                "cse_tok": cse_token,
                "exp": "csqr,cc,4861325",
                "callback": "google.search.cse.api8659",
            }
        )
        return "https://cse.google.com/cse/element/v1?" + params

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.default)
    async def enigma2(self, ctx: commands.Context, *, query: str):
        """Recreates a DVB-S ServiceReference ID present in enigma2 based on LyngSat data."""
        headers = {"User-Agent": self.bot.user_agent}
        advice_embed = discord.Embed(
            description="You can try finding the channel manually (`CTRL+F`) in the following EPG source list:\n[rytec.channels-sat.xml](https://raw.githubusercontent.com/doglover3920/EPGimport-Sources/main/rytec.channels-sat.xml)",
            color=discord.Color.blue(),
        )

        await ctx.typing()

        query = quote(query)
        cse_url = await self.get_lyngsat_cse_url()
        cse_url += f"&q={query}&oq={query}"

        async with self.bot.session.get(cse_url, headers=headers) as r:
            if not r.ok:
                raise ArtemisError(f"LyngSat CSE returned error: {r.status} {r.reason}")
            data = await r.text()

        data = re.search(r"\"results\":\s*(\[.*?\]),", data, re.S)
        if not data:
            raise ArtemisError("LyngSat CSE returned invalid data.")

        data = json.loads(data.group(1))
        items = [
            item for item in data if "tvchannels" in item["url"] and r"%26sa%3DU" not in item["url"]
        ]

        if not items:
            return await ctx.reply("No results found.", embed=advice_embed)
        elif len(items) == 1:
            result = items[0]
        else:
            view = DropdownView(
                ctx,
                items,
                lambda x: x["titleNoFormatting"].removesuffix(" - LyngSat"),
                lambda x: x["url"].split("tvchannels/")[1].removesuffix(".html"),
            )
            result = await view.prompt("Which channel?")
            if not result:
                return
            await ctx.typing()

        lyngsat_url = result["url"]
        async with self.bot.session.get(lyngsat_url, headers=headers) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "lxml")

        channel = result["titleNoFormatting"].removesuffix(" - LyngSat")

        satellites_table = soup.find(string="Satellite")
        satellites_table = satellites_table.find_parent("table")

        satellites = satellites_table.select("tr")[2:-1]
        satellites = [s for s in satellites if len(s.select("td")) >= 7]

        if len(satellites) == 1:
            result = satellites[0]
        else:

            def satellite_desc(s):
                fields = s.select("td")
                ret = []
                video = fields[6]
                lang = fields[7]
                if video.text:
                    for br in video.select("br"):
                        br.replace_with(" ")
                    ret.append(video.text)
                if lang.text:
                    for br in lang.select("br"):
                        br.replace_with(" ")
                    ret.append(lang.text.lower())
                return ", ".join(ret) if ret else None

            view = DropdownView(ctx, satellites, lambda x: x.select("td")[1].text, satellite_desc)
            result = await view.prompt("Which satellite?")
            if not result:
                return
            await ctx.typing()

        satellite_data = result.select("td")
        satellite_pos = satellite_data[0].text.strip()
        assert satellite_data[1].a
        satellite_url = satellite_data[1].a["href"]

        sat_pos = re.search(r"(\d{1,3}(?:\.\d)?).*?((?:E|W))", satellite_pos)
        if not sat_pos:
            return await ctx.reply("Failed to find satellite position.", embed=advice_embed)

        pos, cardinal = sat_pos.groups()
        # sref Namespace
        ns = enigma2.build_namespace(float(pos), cardinal.upper())

        packages = satellite_data[9].select("a")

        if not packages:
            return await ctx.reply(
                "Extraction for channels without linked providers is not supported due to missing data.",
                embed=advice_embed,
            )
        elif len(packages) == 1:
            package = packages[0]
        else:
            view = DropdownView(ctx, packages, lambda x: x.text)
            package = await view.prompt("Which provider?")
            if not package:
                return
            package = package
            await ctx.typing()

        async with self.bot.session.get(satellite_url, headers=headers) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "lxml")

        cell = soup.find(string=package.text.strip())
        if not cell:
            return await ctx.reply(
                "Could not match provider name to the entries in the satellite's table.",
                embed=advice_embed,
            )

        onid_tid = cell.find_parent("td").find_next_siblings("td")[1].text.strip()
        if not onid_tid:
            return await ctx.reply(
                "Not enough data to recreate a ServiceReference (missing ONID-TID).",
                embed=advice_embed,
            )

        onid_tid = re.search(r"(\d+)-(\d+)", onid_tid)
        if not onid_tid:
            return await ctx.reply(
                "Not enough data to recreate a ServiceReference (invalid ONID-TID).",
                embed=advice_embed,
            )

        onid, package_tid = onid_tid.groups()

        async with self.bot.session.get(package["href"], headers=headers) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "lxml")

        cell = soup.find(string=channel.strip())
        parent = cell.find_parent("td")
        siblings = parent.find_previous_siblings("td")
        sid = siblings[2].text.strip()
        if not sid:
            return await ctx.reply(
                "Not enough data to recreate a ServiceReference (missing SID).", embed=advice_embed
            )

        tid = parent.find_all_previous("td", rowspan=True)[1]
        for br in tid.select("br"):
            br.replace_with("\n")
        tid = re.search(r"tp (\d+)", tid.text)

        if not tid:
            is_guessed_tid = True
            tid = package_tid
        else:
            tid = tid.group(1)
            tid = tid + "00"
            is_guessed_tid = False

        if not sid.isdigit():
            return await ctx.reply(
                "Not enough data to recreate a ServiceReference (invalid SID).", embed=advice_embed
            )

        stype = enigma2.ServiceType.HDTV if "HD" in channel else enigma2.ServiceType.TV

        sref = enigma2.build_sref(stype, int(sid), int(tid), int(onid), ns)
        parsed = enigma2.parse_sref(sref)
        parsed = "\n".join([f"{k.replace('_', '').upper()}: **{v}**" for k, v in parsed.items()])

        embed = discord.Embed(title=channel, url=lyngsat_url, color=0xFFE4B5)
        embed.description = f"{parsed}\n\n`{sref}`\n"

        if is_guessed_tid:
            embed.description += (
                "(TSID assumed from provider's value, channel-specific TSID unavailable)"
            )

        return await ctx.reply(embed=embed)


async def setup(bot: Artemis):
    await bot.add_cog(Useful(bot))
