import json
import time
from base64 import b64decode
from typing import Optional
from urllib.parse import quote

from aiohttp import ClientSession
from yt_dlp.utils import random_user_agent

import utils


class uNoGSError(Exception):
    pass


class uNoGS:
    token: Optional[str]
    token_expiry: Optional[int]

    _API_BASE = "https://unogs.com/api"
    _EMPTY_PARAMS = [
        "country_andorunique",
        "start_year",
        "end_year",
        "start_rating",
        "end_rating",
        "genrelist",
        "type",
        "audio",
        "subtitle",
        "audiosubtitle_andor",
        "person",
        "filterby",
        "orderby",
    ]
    _COUNTRY_LIST = "21,23,26,29,33,36,307,45,39,327,331,334,265,337,336,269,267,357,378,65,67,390,392,268,400,402,408,412,447,348,270,73,34,425,432,436,46,78"
    _DEFAULT_HEADERS = {
        "User-Agent": random_user_agent(),
        "Referer": "https://unogs.com",
        "Referrer": "http://unogs.com",
    }
    _DETAILS = ["detail", "bgimages", "genres", "people", "countries", "episodes"]

    def __init__(self, session: ClientSession):
        self.session: ClientSession = session
        self.token = None
        self.token_expiry = None

    async def _validate_token(self):
        if not self.token or self.token_expiry < utils.time():
            await self._fetch_token()

    async def _fetch_token(self):
        data = {"user_name": round(time.time(), 3)}
        async with self.session.post(
            self._API_BASE + "/user", headers=self._DEFAULT_HEADERS, data=data
        ) as r:
            data = await r.json()

        token = data["token"]["access_token"]
        self.token = token
        token_data = token.split(".")[1] + "=="
        token_data = b64decode(token_data).decode()
        self.token_expiry = json.loads(token_data)["exp"]

    async def _request(self, path: str, **kwargs):
        await self._validate_token()
        headers = {**self._DEFAULT_HEADERS, "Authorization": f"Bearer {self.token}"}
        cookies = {"authtoken": "token"}

        async with self.session.get(
            self._API_BASE + path, headers=headers, cookies=cookies, **kwargs
        ) as r:
            return await r.json()

    async def search(self, query: str):
        params = {
            "limit": "20",
            "offset": "0",
            "query": quote(query),
            "countrylist": self._COUNTRY_LIST,
        }
        for param in self._EMPTY_PARAMS:
            params[param] = ""
        return await self._request("/search", params=params)

    async def fetch_details(self, nfid, kind="detail"):
        if kind not in self._DETAILS:
            raise uNoGSError("Incorrect detail kind.")
        return await self._request(f"/title/{kind}", params={"netflixid": nfid})
