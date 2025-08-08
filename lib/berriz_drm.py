import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from cookies.cookies import Refresh_JWT, Berriz_cookie
from lib.download import run_dl
from key.msprpro import GetMPD_prd
from key.pssh import GetMPD_wv
from key.GetClearKey import get_clear_key
from key.local_vault import LocalKeyVault
from static.PlaybackInfo import PlaybackInfo
from static.PublicInfo import PublicInfo

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class VodProcess:

    def __init__(self):
        Refresh_JWT.main()
        self.cookies = Berriz_cookie()._cookies
        self.headers = self._build_headers()

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Host": "svc-api.berriz.in",
            "Referer": "https://berriz.in/",
            "Accept": "application/json",
            "Origin": "https://berriz.in",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; iPhone17.6.1; fanz-ios 1.1.4; iPhone12,3",
        }

    def _send_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:

        try:
            response = requests.get(
                url,
                params=params,
                cookies=self.cookies,
                headers=self.headers,
                verify=True,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
            return None


class Playback_info(VodProcess):

    UUID_REGEX = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    def get_playback_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and self.UUID_REGEX.match(media_id):
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/playback_info"
                if data := self._send_request(url):
                    results.append(data)
        return results


class Public_context(VodProcess):

    UUID_REGEX = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    def get_public_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and self.UUID_REGEX.match(media_id):
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/public_context"
                if data := self._send_request(url):
                    results.append(data)
        return results


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
            logging.error(f"Error code: {self.playback_info.code}", self.playback_info)
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
                pass
            else:
                logging.error(f"Key verification FAILED for: {k}")

    def search_keys(self):
        vault = LocalKeyVault()
        wv_pssh_value = vault.retrieve(self.wv_pssh)
        msprpro_value = vault.retrieve(self.msprpro)
        if msprpro_value or wv_pssh_value is not None:
            logging.info(f"Use local key vault keys: {msprpro_value}")
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
            print(f"\n=== Process context #{i+1} ===")

            playback_info = PlaybackInfo(playback_ctx)
            public_info = PublicInfo(public_ctx)
            self.all_playback_infos.append((playback_info, public_info))

            # Handle DRM and obtain information needed for download
            key_handler = Key_handle(playback_info, self.media_id)
            key, media_id_from_drm, dash_playback_url = key_handler.send_drm()

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

        print("\n=== All content processed ===")
        logging.info(f"Total number of media processed: {len(self.all_playback_infos)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    media_id = "01972e78-9808-11ff-853e-c47a923aeb4a"
    processor = BerrizProcessor(media_id)
    asyncio.run(processor.run())
