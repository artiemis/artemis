import os
from utils.common import read_toml
from dataclasses import dataclass


@dataclass
class Keys:
    api: str
    catbox: str
    github: str
    cloudflare: str
    openai: str


@dataclass
class Config:
    token: str
    prefix: str
    user_agent: str
    real_user_agent: str
    api_base_url: str
    cdn_base_url: str
    main_guild_id: int
    dev_guild_id: int
    keys: Keys

    def __post_init__(self):
        self.keys = Keys(**self.keys)  # type: ignore


def load_config() -> Config:
    if os.getenv("ENV") == "production":
        config = read_toml("config.prod.toml")
    else:
        config = read_toml("config.dev.toml")

    return Config(**config)


config = load_config()
