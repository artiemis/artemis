import re

from discord.ext import commands


class _PosArgSentinel:
    pass


PosArgument = _PosArgSentinel


class Flags:
    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def __repr__(self) -> str:
        args = []
        for name, value in self.__dict__.items():
            args.append(f"{name}={value!r}")
        return f"Flags({', '.join(args)})"


class FlagConverter(commands.Converter):
    """Custom command flags converter and parser."""

    async def convert(self, ctx: commands.Context, argument: str):
        flags = self.__class__.__annotations__
        if not flags:
            raise ValueError("No flags provided.")

        parsed_flags = {}
        for name, type in flags.items():
            if type is PosArgument:
                value = re.sub(r"[a-zA-Z]+:[^\s\/]+", "", argument)
                parsed_flags[name] = value.strip()
            else:
                m = re.search(rf"(\b{name}|\b{name[0]}):(?P<value>[^\s\/]+)\b", argument)
                if m:
                    value = m.group("value")
                    parsed_flags[name] = value
                else:
                    parsed_flags[name] = None
        return Flags(**parsed_flags)


class TranslateFlags(FlagConverter):
    text: PosArgument
    source: str
    dest: str


class TTSFlags(FlagConverter):
    text: PosArgument
    lang: str


class WiktionaryFlags(FlagConverter):
    phrase: PosArgument
    lang: str


class DLFlags(FlagConverter):
    url: PosArgument
    format: str
    trim: str
    name: str
    ss: str
    bypass: str


class WikipediaFlags(FlagConverter):
    query: PosArgument
    lang: str


class OCRFlags(FlagConverter):
    url: PosArgument
    lang: str


class OCRTranslateFlags(FlagConverter):
    url: PosArgument
    lang: str
    source: str
    dest: str
