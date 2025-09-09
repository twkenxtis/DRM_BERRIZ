import asyncio
import json
from typing import Any, List, Tuple
from functools import cache

from lib.download import run_dl
from key.msprpro import GetMPD_prd
from key.pssh import GetMPD_wv
from key.GetClearKey import get_clear_key
from key.local_vault import SQLiteKeyVault
from static.PlaybackInfo import PlaybackInfo, LivePlaybackInfo
from static.PublicInfo import PublicInfo
from static.color import Color
from static.api_error_handle import api_error_handle
from unit.http.request_berriz_api import Playback_info, Public_context, Live
from unit.handle_log import setup_logging
from unit.parameter import paramstore


logger = setup_logging('berriz_drm', 'tomato')


class Key_handle:
    def __init__(self, playback_info, media_id, raw_mpd):
        self.playback_info = playback_info
        self.dash_playback_url = self.playback_info.dash_playback_url
        self.assertion = self.playback_info.assertion
        self._msprpro = None
        self._wv_pssh = None
        self.media_id = media_id
        self.raw_mpd = raw_mpd
        self.drm_type = 'mspr'

    @property
    def msprpro(self):
        if self._msprpro is None and self.raw_mpd:
            self._msprpro = GetMPD_prd.parse_pssh(self.raw_mpd)
        return self._msprpro

    @property
    def wv_pssh(self):
        if self._wv_pssh is None and self.raw_mpd:
            self._wv_pssh = GetMPD_wv.parse_pssh(self.raw_mpd)
        return self._wv_pssh

    async def send_drm(self):
        if self.playback_info.code != "0000":
            logger.error(f"Error code: {self.playback_info.code}", self.playback_info)
            raise Exception(f"Invalid response code: {self.playback_info.code}")
        
        if hasattr(self.playback_info, "duration"):
            if self.playback_info.is_drm:
                wv_pssh_value, msprpro_value = await self.search_keys()

                if msprpro_value is not None:
                    key = msprpro_value
                    return key, self.media_id, self.dash_playback_url
                key = await self.request_keys()
                return list(key), self.media_id, self.dash_playback_url
            
    async def drm_choese(self):
        if self.drm_type == 'mspr':
            p = self._msprpro
        elif self.drm_type == 'wv':
            p = self._wv_pssh
        elif self.drm_type == 'watora_wv':
            p = self._wv_pssh
        elif self.drm_type == 'cdrm_wv':
            p = self._wv_pssh
        elif self.drm_type == 'cdrm_mspr':
            p = self._msprpro
        else:
            p = self._wv_pssh
        return p

    async def save_key(self, key):
        vault = SQLiteKeyVault()
        if key is None:
            logger.error("Key is None. Cannot save to vault.")
            return

        await asyncio.gather(
            vault.store_single(self.wv_pssh, key, drm_type="wv"),
            vault.store_single(self.msprpro, key, drm_type="mspr")
        )

        for k in [self.wv_pssh, self.msprpro]:
            drm_type = 'wv' if len(k) > 76 else 'mspr'
            if vault.contains(k):
                logger.info(f"{Color.fg('iceberg')}SUCCESS save key to local vault:{Color.reset()} "
                            f"{Color.fg('gold')}{key}{Color.reset()} - {Color.fg('ruby')}{drm_type}{Color.reset()}"
                            )
            else:
                logger.error(f"Key verification FAILED for: {k}")

    async def search_keys(self):
        vault = SQLiteKeyVault()
        results = await asyncio.gather(
            vault.retrieve(self.wv_pssh),
            vault.retrieve(self.msprpro)
        )
        wv_pssh_value, msprpro_value = results
        if msprpro_value or wv_pssh_value is not None:
            logger.info(f"{Color.fg('mint')}Use local key vault keys:{Color.reset()} {Color.fg('ruby')}{msprpro_value}{Color.reset()}")
            return wv_pssh_value, msprpro_value
        return (None, None)

    async def request_keys(self):
        """wv mspr cdrm watora"""
        request_pssh = await self.drm_choese()
        keys = await get_clear_key(request_pssh, self.assertion, self.drm_type)
        
        if keys:
            for key in keys:
                await self.save_key(key)
            return keys
        else:
            logger.error("No keys received")
            return None


async def start_download(public_info, key, dash_playback_url):
    if public_info.code == "0000":
        json_data = json.loads(public_info.to_json())
    
    if paramstore.get('key') is True:
        logger.info(
            f"{Color.fg('light_gray')}title:{Color.reset()} "
            f"{Color.fg('olive')}{json_data.get('media', {}).get('title', '')}{Color.reset()}"
        )
        logger.info(f"{Color.fg('light_gray')}MPD: {Color.fg('dark_cyan')}{dash_playback_url} {Color.reset()}")
    else:
        raw_mpd = await Live().fetch_mpd(dash_playback_url)
        await asyncio.create_task(run_dl(dash_playback_url, key, json_data, raw_mpd))


class BerrizProcessor:
    def __init__(self, media_id: str, media_type:str):
        self.media_id = media_id
        self.media_type = media_type
        self.all_playback_infos: List[Tuple[PlaybackInfo, PublicInfo]] = []
        self._tasks: List[asyncio.Task] = []
        self._playback_contexts: List[Any] = []
        self._public_contexts: List[Any] = []

    async def fetch_contexts(self):
        # Live-replay and VOD different
        if self.media_type == 'VOD':
            playback, public = await asyncio.gather(
                Playback_info().get_playback_context(self.media_id),
                Public_context().get_public_context(self.media_id),
            )
        elif self.media_type == 'LIVE':
            playback, public = await asyncio.gather(
                Playback_info().get_live_playback_info(self.media_id),
                Public_context().get_public_context(self.media_id),
            )
        self._playback_contexts = playback
        self._public_contexts = public

    async def prepare_download_tasks(self):
        for playback_ctx, public_ctx in zip(
            self._playback_contexts, self._public_contexts
        ):  
            if self.media_type == 'VOD':
                playback_info, public_info = await asyncio.gather(
                    asyncio.to_thread(PlaybackInfo, playback_ctx),
                    asyncio.to_thread(PublicInfo,  public_ctx),
                )
            elif self.media_type == 'LIVE':
                playback_info, public_info = await asyncio.gather(
                    asyncio.to_thread(LivePlaybackInfo, playback_ctx),
                    asyncio.to_thread(PublicInfo,  public_ctx),
                )
            self.all_playback_infos.append((playback_info, public_info))
            
            # Handle DRM and obtain information needed for download
            if playback_info.code != "0000":
                logger.warning(f"{Color.bg('maroon')}{api_error_handle(playback_info.code)}{Color.reset()}")
                return
            elif playback_info.is_drm is True:
                raw_mpd = await Live().fetch_mpd(playback_info.dash_playback_url)
                key_handler = Key_handle(playback_info, self.media_id, raw_mpd)
                logger.info(f"{Color.fg('orange')}{key_handler.wv_pssh}{Color.reset()}")
                logger.info(f"{Color.fg('yellow')}{key_handler.msprpro}{Color.reset()}")
                
                k = await key_handler.send_drm()
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

    @cache
    async def execute_downloads(self):
        if not self._tasks:
            return
        await asyncio.gather(*self._tasks)

    async def run(self):
        await asyncio.gather(self.fetch_contexts())
        await self.prepare_download_tasks()
        await asyncio.create_task(self.execute_downloads())
        
    async def check_vod_isLive(self):
        return