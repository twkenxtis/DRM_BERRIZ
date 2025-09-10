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
from lib.ffmpeg.parse_m3u8 import rebuild_master_playlist
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
        self.drm_type = 'wv'

    @property
    def msprpro(self):
        if self._msprpro is None and self.raw_mpd:
            self._msprpro = GetMPD_prd.parse_pssh(self.raw_mpd)
            self._msprpro[:] = list(set(self._msprpro))
        return self._msprpro

    @property
    def wv_pssh(self):
        if self._wv_pssh is None and self.raw_mpd:
            self._wv_pssh = GetMPD_wv.parse_pssh(self.raw_mpd)
            self._wv_pssh[:] = list(set(self._wv_pssh))
        return self._wv_pssh

    async def send_drm(self):
        if self.playback_info.code != "0000":
            logger.error(f"Error code: {self.playback_info.code}", self.playback_info)
            raise Exception(f"Invalid response code: {self.playback_info.code}")
        
        if hasattr(self.playback_info, "duration"):
            if self.playback_info.is_drm:
                key = await self.search_keys()

                if key is not None:
                    return key, self.media_id
                key = await self.request_keys()
                return list(key), self.media_id
            
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

    async def save_key(self, key: str) -> None:
        vault = SQLiteKeyVault()
        if not key:
            logger.error("Key is None. Cannot save to vault.")
            return

        async def _store_and_log(pssh: str, drm: str):
            await vault.store_single(pssh, key, drm)
            exists = vault.contains(pssh)
            tag, reset = Color.fg("iceberg"), Color.reset()
            if exists:
                logger.info(
                    f"{tag}SUCCESS save key to local vault:{reset} "
                    f"{Color.fg('gold')}{key}{reset} - "
                    f"{Color.fg('ruby')}{drm}{reset}"
                )
            else:
                logger.error(f"Key verification FAILED for: {pssh}")

        jobs = []
        if self.wv_pssh:
            for wv_pssh in self.wv_pssh:
                jobs.append(_store_and_log(wv_pssh, "wv"))
        if self.msprpro:
            for mspr_pssh in self.msprpro:
                jobs.append(_store_and_log(mspr_pssh, "mspr"))
        if jobs:
            await asyncio.gather(*jobs)

    async def search_keys(self):
        vault = SQLiteKeyVault()
        if self.wv_pssh:
            for all_pssh in self.wv_pssh:
                wv = await vault.retrieve(all_pssh)
        if self.msprpro:
            for all_pssh in self.msprpro:
                ms_pr = await vault.retrieve(all_pssh)
            key = ms_pr or wv 
            if key is not None:
                logger.info(f"{Color.fg('mint')}Use local key vault keys:{Color.reset()} {Color.fg('ruby')}{key}{Color.reset()}")
                return key
        return (None)

    async def request_keys(self):
        """wv mspr cdrm watora"""
        request_pssh = await self.drm_choese()
        for pssh in request_pssh:
            keys = await get_clear_key(pssh, self.assertion, self.drm_type)
            
            if keys:
                for key in keys:
                    await self.save_key(key)
                return keys
            else:
                logger.error("No keys received")
                return None


async def start_download(public_info, key, raw_mpd, dash_playback_url, hls_playback_url, raw_hls):
    if public_info.code == "0000":
        json_data = json.loads(public_info.to_json())
    
    if paramstore.get('key') is True:
        logger.info(
            f"{Color.fg('light_gray')}title:{Color.reset()} "
            f"{Color.fg('olive')}{json_data.get('media', {}).get('title', '')}{Color.reset()}"
        )
        logger.info(f"{Color.fg('khaki')}MPD: {Color.fg('dark_cyan')}{dash_playback_url} {Color.reset()}")
        logger.info(f"{Color.fg('sky_blue')}HLS: {Color.fg('dark_cyan')}{hls_playback_url} {Color.reset()}")
    else:
        logger.info(f"{Color.fg('khaki')}MPD: {Color.fg('dark_cyan')}{dash_playback_url} {Color.reset()}")
        logger.info(f"{Color.fg('sky_blue')}HLS: {Color.fg('dark_cyan')}{hls_playback_url} {Color.reset()}")
        await asyncio.create_task(run_dl(dash_playback_url, key, json_data, raw_mpd, hls_playback_url, raw_hls))


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
            
            key, dash_playback_url, raw_mpd, hls_playback_url, raw_hls = await asyncio.create_task(self.drm_handle(playback_info))
            await self.create_task(public_info, key, raw_mpd, dash_playback_url, hls_playback_url, raw_hls)

    async def drm_handle(self, playback_info):
        # Handle DRM and obtain information needed for download
        if playback_info.code != "0000":
            logger.warning(f"{Color.bg('maroon')}{api_error_handle(playback_info.code)}{Color.reset()}")
            return

        if playback_info.dash_playback_url:
            raw_mpd = await Live().fetch_mpd(playback_info.dash_playback_url)
        if playback_info.hls_playback_url:
            response_hls = await Live().fetch_mpd(playback_info.hls_playback_url)
            raw_hls = await rebuild_master_playlist(response_hls, playback_info.hls_playback_url)
        if playback_info.is_drm is True:
            key_handler = Key_handle(playback_info, self.media_id, raw_mpd)
            await self.print_drm_info(key_handler)
            pk = await key_handler.send_drm()
            key, media_id_from_drm = pk
        elif playback_info.is_drm is False:
            key = None
        else:
            logger.error(f"Invalid DRM status for media ID: {self.media_id}")
            raise Exception(f"Check {playback_info.dash_playback_url} PSSH or DRM info !")
        
        dash_playback_url = playback_info.dash_playback_url
        hls_playback_url = playback_info.hls_playback_url
        return key, dash_playback_url, raw_mpd, hls_playback_url, raw_hls

    async def create_task(self, public_info, key, raw_mpd, dash_playback_url, hls_playback_url, raw_hls):
        task = asyncio.create_task(
            start_download(public_info, key, raw_mpd, dash_playback_url, hls_playback_url, raw_hls)
        )
        self._tasks.append(task)

    async def print_drm_info(self, key_handler):
        k = key_handler.wv_pssh
        p = key_handler.msprpro
        if k is not None and isinstance(k, list):
            k_print ='\n'.join(k)
            logger.info(f"{Color.fg('iron')}PSSH: "
                        f"{Color.fg('orange')}{k_print}{Color.reset()}"
                        )
            logger.info(
                f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                f"{Color.fg('bright_cyan')}Widevine{Color.reset()}"
            )
        if p is not None and isinstance(p, list):
            p_print = '\n'.join(p)
            logger.info(f"{Color.fg('iron')}PSSH: "
                f"{Color.fg('yellow')}{p_print}{Color.reset()}"
                )
            logger.info(
                f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                f"{Color.fg('bright_cyan')}PlayReady{Color.reset()}"
            )
        
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