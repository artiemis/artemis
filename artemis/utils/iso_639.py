from __future__ import annotations

import json
import re
from csv import DictReader
from io import StringIO
from typing import TYPE_CHECKING, Literal, TypedDict

from .common import fuzzy_search, read_json

if TYPE_CHECKING:
    from ..bot import Artemis


class Language(TypedDict):
    id: str
    part1: str
    part2b: str
    part2t: str
    name: str


class NameResult(TypedDict):
    name: str
    source: str


class CodeResult(TypedDict):
    name: str
    part1: str
    part2b: str
    part2t: str
    part3: str


SearchMethod = Literal["fuzzy", "strict-start", "strict"]


iso_639_1: list[Language] = []
iso_639_2b: list[Language] = []
iso_639_3: list[Language] = []

try:
    iso_639_3 = read_json("data/iso_639_3.json")

    iso_639_1 = [entry for entry in iso_639_3 if entry["part1"]]
    iso_639_2b = [entry for entry in iso_639_3 if entry["part2b"]]
except FileNotFoundError:
    pass


def _find_entry(seq: list[Language], lookup_key: str, query: str) -> Language | None:
    return next((entry for entry in seq if entry[lookup_key] == query), None)


def get_language_name(code: str):
    code = code.strip().lower()
    if not code:
        return None

    found = None

    # iso 639-1 alpha2 codes
    if len(code) == 2:
        found = _find_entry(iso_639_1, "part1", code)
        if found:
            found = found["name"]
    # alpha3 codes
    elif len(code) == 3:
        # try iso-639-3 first
        found = _find_entry(iso_639_3, "id", code)
        if found:
            found = found["name"]
        else:
            # try iso-639-2b
            found = _find_entry(iso_639_2b, "part2b", code)
            if found:
                found = found["name"]

    return found


def get_language_code(name: str, method: SearchMethod = "fuzzy") -> list[CodeResult] | None:
    name = name.strip().lower()
    if not name:
        return None

    if method == "fuzzy":
        found = fuzzy_search(name, iso_639_3, "name", cutoff=80)
    elif method == "strict-start":
        found = [entry for entry in iso_639_3 if re.search(rf"^{name}\b", entry["name"], re.I)]
    elif method == "strict":
        found = [entry for entry in iso_639_3 if entry["name"].lower() == name]

    if not found:
        return None

    return [
        {
            "name": entry["name"],
            "part3": entry["id"],
            "part2b": entry["part2b"],
            "part2t": entry["part2t"],
            "part1": entry["part1"],
        }
        for entry in found
    ]


async def build(bot: Artemis):
    url = "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab"
    headers = {"User-Agent": bot.user_agent}

    async with bot.session.get(url, headers=headers) as r:
        data = await r.text()

    data = DictReader(StringIO(data), delimiter="\t")

    clean_data = []
    for entry in data:
        entry = {
            k.lower(): v for k, v in entry.items() if k not in ("Scope", "Language_Type", "Comment")
        }

        for k in entry:
            if not entry[k]:
                entry[k] = None

        entry["name"] = entry.pop("ref_name")

        clean_data.append(entry)

    with open("data/iso_639_3.json", "w") as f:
        json.dump(clean_data, f)

    global iso_639_3
    iso_639_3 = clean_data
    return len(clean_data)
