import asyncio
import os
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Any, List, Tuple

from lib.download import run_dl
from key.msprpro import GetMPD_prd
from key.pssh import GetMPD_wv
from key.GetClearKey import get_clear_key
from key.local_vault import LocalKeyVault
from static.PlaybackInfo import PlaybackInfo
from static.PublicInfo import PublicInfo
from unit.http.request_berriz_api import Playback_info, Public_context
from static.color import Color


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger("berriz_drm")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    logger.propagate = False

    # console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # rotating file handler
    app_file_handler = TimedRotatingFileHandler(
        filename="logs/berriz_drm.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


logger = setup_logging()


class Key_handle:
    def __init__(self, playback_info, media_id):
        self.playback_info = playback_info
        self.dash_playback_url = self.playback_info.dash_playback_url
        self.assertion = self.playback_info.assertion
        self.msprpro = GetMPD_prd.parse_pssh(self.dash_playback_url)
        self.wv_pssh = GetMPD_wv.parse_pssh(self.dash_playback_url)
        self.media_id = media_id

    def send_drm(self):
        if self.playback_info.code != "0000":
            logger.error(f"Error code: {self.playback_info.code}", self.playback_info)
            raise Exception(f"Invalid response code: {self.playback_info.code}")

        if hasattr(self.playback_info, "duration"):
            if self.playback_info.is_drm:
                wv_pssh_value, msprpro_value = self.search_keys()
                if msprpro_value is not None:
                    key = msprpro_value
                    return key, self.media_id, self.dash_playback_url
                key = self.request_keys()
                return key, self.media_id, self.dash_playback_url

    def save_key(self, key):
        vault = LocalKeyVault()
        data_to_store = {self.wv_pssh: key, self.msprpro: key}
        vault.store(data_to_store)

        for k in [self.wv_pssh, self.msprpro]:
            if vault.contains(k):
                logger.info(f"{Color.fg('iceberg')}SUCCESS save key to local vault:{Color.reset()} {Color.fg('gold')}{key}{Color.reset()}")
                pass
            else:
                logger.error(f"Key verification FAILED for: {k}")

    def search_keys(self):
        vault = LocalKeyVault()
        wv_pssh_value = vault.retrieve(self.wv_pssh)
        msprpro_value = vault.retrieve(self.msprpro)
        if msprpro_value or wv_pssh_value is not None:
            logger.info(f"{Color.fg('mint')}Use local key vault keys:{Color.reset()} {Color.fg('ruby')}{msprpro_value}{Color.reset()}")
            return wv_pssh_value, msprpro_value
        return (None, None)

    def request_keys(self):
        key = get_clear_key(self.msprpro, self.assertion)
        self.save_key(key)
        return key


async def start_download(public_info, key, dash_playback_url):
    if public_info.code == "0000":
        json_data = public_info.to_json()
    await run_dl(dash_playback_url, key, json.loads(json_data))


class BerrizProcessor:
    def __init__(self, media_id: str):
        self.media_id = media_id
        self.all_playback_infos: List[Tuple[PlaybackInfo, PublicInfo]] = []
        self._tasks: List[asyncio.Task] = []
        self._playback_contexts: List[Any] = []
        self._public_contexts: List[Any] = []

    async def fetch_contexts(self):
        self._playback_contexts = Playback_info().get_playback_context(self.media_id)
        self._public_contexts = Public_context().get_public_context(self.media_id)

    async def prepare_download_tasks(self):
        for i, (playback_ctx, public_ctx) in enumerate(
            zip(self._playback_contexts, self._public_contexts)
        ):
            playback_info = PlaybackInfo(playback_ctx)
            public_info = PublicInfo(public_ctx)
            self.all_playback_infos.append((playback_info, public_info))

            # Handle DRM and obtain information needed for download
            if playback_info.is_drm is True:
                key_handler = Key_handle(playback_info, self.media_id)
                k = key_handler.send_drm()
                key, media_id_from_drm, dash_playback_url = k
            elif playback_info.is_drm is False:
                dash_playback_url = playback_info.dash_playback_url
                key = None
            else:
                logger.error(f"Invalid DRM status for media ID: {self.media_id}")
                raise Exception(f"Check {playback_info.dash_playback_url} PSSH or DRM info !")
            await self.create_task(public_info, key, dash_playback_url)

    async def create_task(self, public_info, key, dash_playback_url):
        task = asyncio.create_task(
            start_download(public_info, key, dash_playback_url)
        )
        self._tasks.append(task)

    async def execute_downloads(self):
        if not self._tasks:
            return
        await asyncio.gather(*self._tasks)

    async def run(self):
        await self.fetch_contexts()
        await self.prepare_download_tasks()
        await self.execute_downloads()