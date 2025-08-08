import asyncio
import errno
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import aiofiles
import aiohttp
import jwt
import m3u8
import requests
from colorama import Fore, Style, init
from dataclasses import dataclass
from tabulate import tabulate
from tqdm.asyncio import tqdm

from cookies import Refresh_JWT, Berriz_cookie
from PlaybackInfo import PlaybackInfo
from PublicInfo import PublicInfo
from msprpro import GetMPD
from GetClearKey import get_clear_key
from download import MediaDownloader, run_dl

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class LiveVodProcess:

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


class Playback_info(LiveVodProcess):

    UUID_REGEX = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    def get_playback_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and self.UUID_REGEX.match(
                media_id
            ):
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/playback_info"
                if data := self._send_request(url):
                    results.append(data)
        return results
    

class Public_context(LiveVodProcess):

    UUID_REGEX = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    def get_public_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and self.UUID_REGEX.match(
                media_id
            ):
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/public_context"
                if data := self._send_request(url):
                    results.append(data)
        return results

def send_drm(playback_info, media_id):
    if playback_info.code != '0000':
        logging.error(f"Error code: {playback_info.code}", playback_info)
        raise Exception(f"Invalid response code: {playback_info.code}")
    
    if hasattr(playback_info, 'duration'):
        if playback_info.is_drm:
            dash_playback_url = playback_info.dash_playback_url
            msprpro = GetMPD.parse_pssh(dash_playback_url)
            assertion = playback_info.assertion
            key = get_clear_key(msprpro, assertion)
            return key, media_id, dash_playback_url


async def start_download(public_info, key, dash_playback_url):
    if public_info.code == '0000':
        json_data = public_info.to_json()
        
    await run_dl(dash_playback_url, key, json.loads(json_data))

async def main():
    media_id = '01972e78-9808-11ff-853e-c47a923aeb4a'
    playback_contexts = Playback_info().get_playback_context(media_id)
    public_context = Public_context().get_public_context(media_id)
    
    all_playback_infos = []
    tasks = []

    for i, (playback_ctx, public_info) in enumerate(zip(playback_contexts, public_context)):
        playback_info = PlaybackInfo(playback_ctx)
        public_info = PublicInfo(public_info)
        all_playback_infos.append((playback_info, public_info))
        
        print(f"\n=== Processing context #{i+1} ===")

        key, media_id, dash_playback_url = send_drm(playback_info, media_id)
        
        task = start_download(public_info, key, dash_playback_url)
        tasks.append(task)

    # 并行执行所有任务
    await asyncio.gather(*tasks)

    print("\n=== All content processed ===")
    print(f"Total media processed: {len(all_playback_infos)}")
    
if __name__ == "__main__":
    asyncio.run(main())
