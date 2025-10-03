import asyncio
import re
import yaml

from pathlib import Path
from functools import lru_cache

import aiofiles

import httpagentparser

from static.color import Color
from unit.handle.handle_log import setup_logging


YAML_PATH: Path = Path(__file__).parent.parent.joinpath('config', 'berrizconfig.yaml')


logger = setup_logging('unit.__init__', 'green')


class ConfigLoader:
    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, path: Path = YAML_PATH) -> dict:
        """同步介面，快取並返回完整、驗證過的 config 字典。"""
        config = asyncio.run(cls._load_async(path))
        return config

    @staticmethod
    async def _load_async(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()

        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML: {e}")
CFG = ConfigLoader.load()
 

def is_user_agent(ua: str) -> bool:
    if not ua or not isinstance(ua, str):
        return False
    parsed = httpagentparser.detect(ua)
    return bool(parsed.get('platform') or parsed.get('browser'))


def get_useragent() -> str:
    USERAGENT = CFG['headers']['User-Agent']
    try:
        if USERAGENT is None:
            raise AttributeError
        if is_user_agent(USERAGENT) is False:
            raise AttributeError
    except AttributeError:
        logger.warning(f"Unsupported User-Agent: {Color.bg('ruby')}{USERAGENT}{Color.fg('gold')}, try default setting to continue ...")
        USERAGENT = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6_1 like Mac OS X) AppleWebKit/605.1.16 (KHTML, like Gecko) Mobile/15E148; iPhone18.6.1; iPhone17,2'
        logger.info(USERAGENT)
    return USERAGENT
USERAGENT = get_useragent()


