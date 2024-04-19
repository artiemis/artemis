import asyncio
import io
import os
from typing import Dict, Literal, Optional

import aiohttp

from .common import is_valid_url

Expiration = Literal[1, 12, 24, 72]


class CatboxError(Exception):
    pass


class BoxBase:
    userhash: Optional[str]
    API_URL: str

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _request(self, data: Dict, timeout: int | None = None) -> str:
        if hasattr(self, "userhash"):
            data["userhash"] = self.userhash

        client_timeout = aiohttp.ClientTimeout(total=timeout or 120)
        try:
            async with self.session.post(self.API_URL, data=data, timeout=client_timeout) as r:
                resp = await r.text()
                if 200 <= r.status < 400:
                    return resp
                else:
                    raise CatboxError(resp)
        except asyncio.TimeoutError:
            raise CatboxError("Upload timed out.")

    async def _aioread(self, fp) -> bytes:
        return await asyncio.to_thread(fp.read)


class Catbox(BoxBase):
    API_URL = "https://catbox.moe/user/api.php"

    def __init__(self, userhash: str, session: aiohttp.ClientSession):
        super().__init__(session=session)
        self.userhash = userhash or ""

    async def upload(self, resource: str | io.IOBase | os.PathLike, timeout: int | None = None):
        fp = None
        url = None
        data = {}

        if isinstance(resource, str):
            if is_valid_url(resource):
                url = resource
            elif os.path.isfile(resource):
                with open(resource, "rb") as f:
                    name = f.name.split("/")[-1]
                    fp = io.BytesIO(await self._aioread(f))
                    fp.name = name
            else:
                raise CatboxError("Invalid file path or URL.")
        elif isinstance(resource, io.IOBase):
            fp = resource
        else:
            raise CatboxError("Invalid file buffer, path or URL.")

        if url:
            data = {"reqtype": "urlupload", "url": url}
        elif fp:
            data = {"reqtype": "fileupload", "fileToUpload": fp}

        return await self._request(data, timeout=timeout)

    async def delete(self, files: str, timeout: int | None = None):
        data = {"reqtype": "deletefiles", "files": files}
        return await self._request(data, timeout=timeout)


class Litterbox(BoxBase):
    API_URL = "https://litterbox.catbox.moe/resources/internals/api.php"

    async def upload(
        self, fp: io.IOBase | os.PathLike, time: Expiration = 1, timeout: int | None = None
    ):
        if time not in (1, 12, 24, 72):
            raise CatboxError("Invalid expiration time.")

        if isinstance(fp, str):
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    name = f.name.split("/")[-1]
                    fp = io.BytesIO(await self._aioread(f))
                    fp.name = name
            else:
                raise CatboxError("Invalid file path.")
        elif isinstance(fp, io.IOBase):
            pass
        else:
            raise CatboxError("Invalid file buffer.")

        data = {"reqtype": "fileupload", "time": f"{time}h", "fileToUpload": fp}

        return await self._request(data, timeout=timeout)
