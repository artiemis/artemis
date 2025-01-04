import os
from dataclasses import dataclass

from .common import read_toml


@dataclass
class Keys:
    api: str
    catbox: str
    github: str
    cloudflare: str
    openai: str
    deepl: str


@dataclass
class Config:
    token: str
    prefix: str
    user_agent: str
    real_user_agent: str
    internal_api_url: str
    cdn_url: str
    main_guild_id: int
    dev_guild_id: int
    keys: Keys

    def __post_init__(self):
        self.keys = Keys(**self.keys)


def load_config() -> Config:
    if os.getenv("ENV") == "production":
        values = read_toml("config.prod.toml")
    else:
        values = read_toml("config.dev.toml")

    return Config(**values)


config = load_config()
