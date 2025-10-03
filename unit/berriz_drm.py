import asyncio
import json
import sys
from typing import Any, List, Tuple, Optional, Dict

from lib.download import run_dl
from lib.mux.parse_m3u8 import rebuild_master_playlist

from key.GetClearKey import get_clear_key
from key.local_vault import SQLiteKeyVault
from key.msprpro import GetMPD_prd
from key.pssh import GetMPD_wv

from static.PlaybackInfo import LivePlaybackInfo, PlaybackInfo
from static.PublicInfo import PublicInfo
from static.api_error_handle import api_error_handle
from static.color import Color

from lib.load_yaml_config import CFG, ConfigLoader

from unit.handle_log import setup_logging
from unit.http.request_berriz_api import Live, Playback_info, Public_context
from unit.parameter import paramstore


logger = setup_logging('berriz_drm', 'tomato')


class Key_handle:
    def __init__(self, playback_info: PlaybackInfo, media_id: str, raw_mpd: Any):
        self.playback_info: PlaybackInfo = playback_info
        self.dash_playback_url: Optional[str] = self.playback_info.dash_playback_url
        self.assertion: Optional[str] = self.playback_info.assertion
        self._msprpro: Optional[List[str]] = None
        self._wv_pssh: Optional[List[str]] = None
        self.media_id: str = media_id
        self.raw_mpd: Any = raw_mpd
        self.drm_type: str = self.drm_type()

    @property
    def msprpro(self) -> Optional[List[str]]:
        if self._msprpro is None and self.raw_mpd:
            self._msprpro = GetMPD_prd.parse_pssh(self.raw_mpd)
            self._msprpro[:] = list(set(self._msprpro))
        return self._msprpro

    @property
    def wv_pssh(self) -> Optional[List[str]]:
        if self._wv_pssh is None and self.raw_mpd:
            self._wv_pssh = GetMPD_wv.parse_pssh(self.raw_mpd)
            self._wv_pssh[:] = list(set(self._wv_pssh))
        return self._wv_pssh

    async def send_drm(self) -> Optional[Tuple[List[str], str]]:
        if self.playback_info.code != "0000":
            logger.error(f"Error code: {self.playback_info.code}", self.playback_info)
            raise Exception(f"Invalid response code: {self.playback_info.code}")
        
        if hasattr(self.playback_info, "duration"):
            if getattr(self.playback_info, "is_drm", None):
                key: Optional[str] = await self.search_keys()

                if key is not None:
                    return [key], self.media_id
                keys = await self.request_keys()
                return (list(keys), self.media_id) if keys else None
        return None
    
    def drm_type(self) -> str:
        drm_type = CFG['KeyService']['source']
        try:
            drm_type = drm_type.lower().strip()
        except AttributeError:
            ConfigLoader.print_warning('DRM-Key Service', drm_type, 'Widevine')
            logger.warning(f"Unsupported drm choese: {Color.bg('ruby')}{drm_type}{Color.fg('gold')}, try choese Widevine to continue ...")
            drm_type = 'wv'

        if drm_type not in('mspr', 'wv', 'watora_wv', 'cdrm_wv', 'cdrm_mspr'):
            drm_type = 'wv'
        return drm_type
         
    async def drm_choese(self) -> Optional[List[str]]:
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

        async def _store_and_log(pssh: str, drm: str) -> None:
            await vault.store_single(pssh, key, drm)
            exists: bool = vault.contains(pssh)
            tag, reset = Color.fg("iceberg"), Color.reset()
            if exists:
                logger.info(
                    f"{tag}SUCCESS save key to local vault:{reset} "
                    f"{Color.fg('gold')}{key}{reset} - "
                    f"{Color.fg('ruby')}{drm}{reset}"
                )
            else:
                logger.error(f"Key verification FAILED for: {pssh}")

        jobs: List[asyncio.Task[Any]] = []
        if self.wv_pssh:
            for wv_pssh in self.wv_pssh:
                jobs.append(asyncio.create_task(_store_and_log(wv_pssh, "wv")))
        if self.msprpro:
            for mspr_pssh in self.msprpro:
                jobs.append(asyncio.create_task(_store_and_log(mspr_pssh, "mspr")))
        if jobs:
            await asyncio.gather(*jobs)

    async def search_keys(self) -> Optional[str]:
        vault = SQLiteKeyVault()
        wv: Optional[str] = None
        ms_pr: Optional[str] = None
        if self.wv_pssh:
            for all_pssh in self.wv_pssh:
                wv = await vault.retrieve(all_pssh)
        if self.msprpro:
            for all_pssh in self.msprpro:
                ms_pr = await vault.retrieve(all_pssh)
            key: Optional[str] = ms_pr or wv 
            if key is not None:
                logger.info(f"{Color.fg('mint')}Use local key vault keys:{Color.reset()} {Color.fg('ruby')}{key}{Color.reset()}")
                return key
        return None

    async def request_keys(self) -> Optional[List[str]]:
        """wv mspr cdrm watora"""
        request_pssh: Optional[List[str]] = await self.drm_choese()
        if not request_pssh:
            return None
        for pssh in request_pssh:
            keys: Optional[List[str]] = await get_clear_key(pssh, self.assertion, self.drm_type)
            
            if keys:
                for key in keys:
                    await self.save_key(key)
                return keys
            else:
                logger.error("No keys received")
                return None
        return None


async def start_download(public_info: PublicInfo, key: Optional[str], raw_mpd: Any, dash_playback_url: str, hls_playback_url: str, raw_hls: str) -> None:
    if public_info.code == "0000":
        json_data: Dict[str, Any] = json.loads(public_info.to_json())
    else:
        json_data = {}
    
    if paramstore.get('key') is True:
        logger.info(
            f"{Color.fg('light_gray')}title:{Color.reset()} "
            f"{Color.fg('olive')}{json_data.get('media', {}).get('title', '')}{Color.reset()}"
        )
        logger.info(f"{Color.fg('khaki')}MPD: {Color.fg('dark_cyan')}{dash_playback_url} {Color.reset()}")
        logger.info(f"{Color.fg('sky_blue')}HLS: {Color.fg('dark_cyan')}{hls_playback_url} {Color.reset()}")
        logger.info(f"{Color.fg('gold')}--key{Color.fg('ruby')} only mode"
                    f"{Color.fg('wheat')} Skip download "
                    f"{BerrizProcessor.print_title(public_info)}"
                    f"{Color.reset()}"
                    )
    else:
        logger.info(f"{Color.fg('khaki')}MPD: {Color.fg('dark_cyan')}{dash_playback_url} {Color.reset()}")
        logger.info(f"{Color.fg('sky_blue')}HLS: {Color.fg('dark_cyan')}{hls_playback_url} {Color.reset()}")
        await run_dl(dash_playback_url, key, json_data, raw_mpd, hls_playback_url, raw_hls)


class BerrizProcessor:
    def __init__(self, media_id: str, media_type: str, selected_media: Dict[str, List[Dict[str, Any]]]):
        self.media_id: str = media_id
        self.media_type: str = media_type
        self.selected_media: dict[str, Any] = selected_media

    async def fetch_contexts(self) -> None:
        # Live-replay and VOD different
        if self.media_type == 'VOD':
            playback, public = await asyncio.gather(
                Playback_info().get_playback_context(self.media_id),
                Public_context().get_public_context(self.media_id),
            )
        elif self.media_type == 'LIVE':
            LP = self.selected_media.get('lives', [])[0]['live']['liveStatus']
            if LP == 'REPLAY':
                playback = await Playback_info().get_live_playback_info(self.media_id)
                public = await Public_context().get_public_context(self.media_id)
        return playback, public

    async def prepare_download_tasks(self, playback, public) -> None:
        match playback:
            case []:
                return False
            case _:
                playback_ctx = playback[0]
                public_ctx = public[0]
                    
                if self.media_type in 'VOD':
                    playback_info, public_info = await asyncio.gather(
                        asyncio.to_thread(PlaybackInfo, playback_ctx),
                        asyncio.to_thread(PublicInfo, public_ctx),
                    )
                elif self.media_type == 'LIVE':
                    playback_info, public_info = await asyncio.gather(
                        asyncio.to_thread(LivePlaybackInfo, playback_ctx),
                        asyncio.to_thread(PublicInfo, public_ctx),
                    )
                return await self.pre_make_download(playback_info, public_info)
    
    async def pre_make_download(self, playback_info: PlaybackInfo, public_info: Playback_info) -> None:
        logger.info(BerrizProcessor.print_title(public_info))

        key, dash_playback_url, raw_mpd, hls_playback_url, raw_hls = await self.drm_handle(playback_info)
        if not any(not v for v in (dash_playback_url, raw_mpd, hls_playback_url, raw_hls)):
            await start_download(public_info, key, raw_mpd, dash_playback_url, hls_playback_url, raw_hls)
        else:
            missing = {
                "dash_playback_url": dash_playback_url,
                "raw_mpd": raw_mpd,
                "hls_playback_url": hls_playback_url,
                "raw_hls": raw_hls
            }
            for name, value in missing.items():
                if not value:
                    logger.warning(f"Missing or invalid: {name} = {repr(value)}")
    
    @staticmethod
    def print_title(public_info: PlaybackInfo):
        return(
            f"{Color.fg('light_magenta')}{public_info.title} {Color.fg('light_cyan')}"
            f"{public_info.artists[0]['name']} {Color.fg('light_gray')}{public_info.media_id}{Color.reset()}"
        )

    async def drm_handle(self, playback_info: Any) -> Tuple[Optional[str], Optional[str], Any, Optional[str], Optional[str]]:
        # Handle DRM and obtain information needed for download
        if getattr(playback_info, "code", None) != "0000":
            logger.warning(f"{Color.bg('maroon')}{api_error_handle(playback_info.code)}{Color.reset()}")
            sys.exit(1)

        raw_mpd: Any = None
        raw_hls: Optional[str] = None

        if getattr(playback_info, "dash_playback_url", None):
            raw_mpd = await Live().fetch_mpd(playback_info.dash_playback_url)
        if getattr(playback_info, "hls_playback_url", None):
            response_hls = await Live().fetch_mpd(playback_info.hls_playback_url)
            raw_hls = await rebuild_master_playlist(response_hls, playback_info.hls_playback_url)
        if getattr(playback_info, "is_drm", None) is True:
            key_handler = Key_handle(playback_info, self.media_id, raw_mpd)
            await self.print_drm_info(key_handler)
            pk = await key_handler.send_drm()
            if pk:
                key_list, media_id_from_drm = pk
                key: Optional[str] = key_list[0] if key_list else None
            else:
                key = None
        elif getattr(playback_info, "is_drm", None) is False:
            key = None
        else:
            logger.error(f"Invalid DRM status for media ID: {self.media_id}")
            raise Exception(f"Check {getattr(playback_info, 'dash_playback_url', None)} PSSH or DRM info !")
        
        dash_playback_url: Optional[str] = getattr(playback_info, "dash_playback_url", None)
        hls_playback_url: Optional[str] = getattr(playback_info, "hls_playback_url", None)
        return key, dash_playback_url, raw_mpd, hls_playback_url, raw_hls

    async def print_drm_info(self, key_handler: Key_handle) -> None:
        k: Optional[List[str]] = key_handler.wv_pssh
        p: Optional[List[str]] = key_handler.msprpro
        if k is not None and isinstance(k, list):
            k_print: str = '\n'.join(k)
            logger.info(f"{Color.fg('iron')}PSSH: "
                        f"{Color.fg('orange')}{k_print}{Color.reset()}"
                        )
            logger.info(
                f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                f"{Color.fg('bright_cyan')}Widevine{Color.reset()}"
            )
        if p is not None and isinstance(p, list):
            p_print: str = '\n'.join(p)
            logger.info(f"{Color.fg('iron')}PSSH: "
                f"{Color.fg('yellow')}{p_print}{Color.reset()}"
                )
            logger.info(
                f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                f"{Color.fg('bright_cyan')}PlayReady{Color.reset()}"
            )

    async def run(self) -> None:
        playback, public = await self.fetch_contexts()
        await self.prepare_download_tasks(playback, public)