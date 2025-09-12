import asyncio
import concurrent.futures
import logging
import os
import re
import threading
from functools import lru_cache
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Union
from unit.parameter import paramstore

import httpx

from lib.lock_cookie import cookie_session, Lock_Cookie
from static.api_error_handle import api_error_handle
from static.color import Color


class NonBlockingFileHandler(TimedRotatingFileHandler):
    """使用線程池執行器實現非阻塞寫入"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="log_writer")
        self._lock = threading.Lock()

    def emit(self, record):
        """在線程池中執行文件寫入"""
        try:
            msg = self.format(record)
            # 在線程池中執行寫入操作（非阻塞）
            self._executor.submit(self._sync_write, msg)
        except Exception as e:
            print(f"Log transmission error: {e}")

    def _sync_write(self, message):
        """同步寫入方法（在線程中執行）"""
        try:
            with self._lock:
                with open(self.baseFilename, 'a', encoding=self.encoding) as f:
                    f.write(message + '\n')
        except Exception as e:
            print(f"File write error: {e}")

    def close(self):
        """關閉處理器"""
        try:
            self._executor.shutdown(wait=True)
        except:
            pass
        super().close()

def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    # 控制台格式（包含顏色）
    console_format = logging.Formatter(
       f"{Color.fg('light_gray')}%(asctime)s [%(levelname)s] [%(name)s]: %(message)s {Color.reset()}"
    )

    # 文件格式（去除所有顏色代碼）
    class NoColorFormatter(logging.Formatter):
        def format(self, record):
            message = super().format(record)
            # 移除所有顏色代碼
            color_pattern = r'(\033\[[0-9;]*m|Color\.\w+\([^)]*\)|Color\.reset\(\))'
            return re.sub(color_pattern, '', message)

    file_format = NoColorFormatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    log_level = logging.INFO

    app_logger = logging.getLogger("request_berriz_api")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_format)

    # 使用非阻塞文件處理器
    app_file_handler = NonBlockingFileHandler(
        filename=os.path.join(log_directory, "request_berriz_api.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(file_format)

    httpx_file_handler = NonBlockingFileHandler(
        filename=os.path.join(log_directory, "httpx_requests.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    httpx_file_handler.setFormatter(file_format)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)

    for logger_name in ["httpx", "httpcore"]:
        lib_logger = logging.getLogger(logger_name)
        lib_logger.setLevel(logging.INFO)
        
        if lib_logger.hasHandlers():
            lib_logger.handlers.clear()
        
        lib_logger.addHandler(console_handler)
        lib_logger.addHandler(httpx_file_handler)
        
        lib_logger.propagate = False

    return app_logger

logger = setup_logging()


UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class BerrizAPIClient:
    
    _re_request_cookie = True
    
    def __init__(self):
        self.headers = self._build_headers()
        self.session = None
        self.connector = None

    @lru_cache(maxsize=1)
    def _build_headers(self) -> Dict[str, str]:
        return {
            "Host": "svc-api.berriz.in",
            "Referer": "https://berriz.in/",
            "Origin": "https://berriz.in",
            "Accept": "application/json",
            'pragma': 'no-cache',
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; iPhone17.6.1; iPhone12,3",
        }
    
    async def cookie(self):
        if cookie_session is None:
            cookie = await Lock_Cookie.cookie_session()
            return cookie
        else:
            return cookie_session

    async def _send_request(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Optional[Dict]:
        try:
            async with httpx.AsyncClient(http2=True, timeout=4, verify=True) as client:
                response = await client.get(
                    url,
                    params=params,
                    cookies = await self.cookie(),
                    headers=headers or self.headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {url}: {e}")
            logger.info(api_error_handle(response.status_code))
            return None
        except httpx.ConnectError as e:
            logger.error(f"Connection error for {url}: {e}")
            return None
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error for {url}: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Unexpected request error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")

    async def _send_request_http1(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None, usecookie = False) -> Optional[Dict]:
        if usecookie is False:
            c = {}
        else:
            c = await self.cookie()
        try:
            async with httpx.AsyncClient(http2=False, timeout=4, verify=True) as client:
                response = await client.get(
                    url,
                    params=params,
                    cookies=c,
                    headers=headers or self.headers,
                )
                response.raise_for_status()
                return response
        except httpx.HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {url}: {e}")
            return None
        except httpx.ConnectError as e:
            logger.error(f"Connection error for {url}: {e}")
            return None
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error for {url}: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Unexpected request error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")


class Playback_info(BerrizAPIClient):
    async def get_playback_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and UUID_REGEX.match(media_id):
                params =  {"languageCode": 'en'}
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/playback_info"
                if data := await self._send_request(url, params=params):
                    results.append(data)
            else:
                logger.warning(f"Invalid media ID format: {media_id}")
        return results

    async def get_live_playback_info(self, media_ids: Union[str, List[str]]) -> List[Dict]:
        """Fetch playback information for given media IDs."""
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and UUID_REGEX.match(media_id):
                params =  {"languageCode": 'en'}
                url = f"https://svc-api.berriz.in/service/v1/medias/live/replay/{media_id}/playback_area_context"
                if data := await self._send_request(url, params=params):
                    results.append(data)
            else:
                logger.warning(f"Invalid media ID format: {media_id}")
        return results

class Public_context(BerrizAPIClient):
    async def get_public_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and UUID_REGEX.match(media_id):
                params =  {"languageCode": 'en'}
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/public_context"
                if data := await self._send_request(url, params=params):
                    results.append(data)
            else:
                logger.warning(f"Invalid media ID format: {media_id}")
        return results
    
class Live(BerrizAPIClient):
    async def request_live_playlist(self, playback_url: str, media_id: str) -> Optional[str]:
        """Request m3u8 playlist."""
        if not playback_url:
            logger.error(f"{Color.fg('light_gray')}No playback URL provided for media_id{Color.reset()}:"
                        f" {Color.fg('turquoise')}{media_id}{Color.reset()}"
                        )
            return None

        headers = {
            **self.headers,
            "Accept": "application/x-mpegURL, application/vnd.apple.mpegurl, application/json, text/plain",
            "Referer": "Berriz/20250704.1139 CFNetwork/1498.700.2 Darwin/23.6.0",
        }

        try:
            if response := await self._send_request(playback_url, headers=headers):
                return response
        except httpx.HTTPError as e:
            logger.error(f"{Color.fg('plum')}Failed to get m3u8 list for media_id{Color.reset()}"
                        f" {Color.fg('turquoise')}{media_id}{Color.reset()}{Color.fg('plum')}: {e}{Color.reset()}"
                        )
            return None
        
    async def fetch_mpd(self, url):
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; iPhone18.3.2; iPhone14,8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'statics.berriz.in',
            'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache',
        }
        return await self._send_request_http1(url, headers=headers, usecookie=False)

    async def fetch_statics(self) -> Optional[Dict]:
        """Fetch static media information for the given media sequence."""
        if self.media_seq is None:
            logger.error("Cannot fetch statics: media_seq is not provided.")
            return None
        url = (
            f"https://svc-api.berriz.in/service/v1/media/statics?"
            f"languageCode=en&mediaSeq={self.media_seq}&t=1"
        )
        return await self._send_request(url)

    async def fetch_chat(self, current_second: int) -> Optional[Dict]:
        """Fetch chat data for the given media sequence and time."""
        if self.media_seq is None:
            logger.error("Cannot fetch chat: media_seq is not provided.")
            return None
        url = (
            f"https://chat-api.berriz.in/chat/v1/sync?"
            f"translateLanguageCode=en&mediaSeq={self.media_seq}&t={current_second}&languageCode=en"
        )
        headers = {
            **self.headers,
            "Host": "chat-api.berriz.in",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        return await self._send_request(url, headers=headers)

    async def fetch_media_seq(self, media_url: str) -> Optional[int]:
        """Fetch mediaSeq from a media URL."""
        headers = {
            **self.headers,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            if response := await self._send_request(media_url, headers=headers):
                data = response.json()
            media_seq = data.get("data", {}).get("media", {}).get("mediaSeq")
            if media_seq is None:
                logger.error("mediaSeq not found in response.")
            else:
                self.media_seq = media_seq  # Update instance media_seq
            return media_seq
        except (httpx.HTTPError, KeyError) as e:
            logger.error(f"Failed to fetch mediaSeq from {media_url}: {e}")
            return None

    async def fetch_live_replay(self, community_id, params) -> Optional[Dict]:
        url = f"https://svc-api.berriz.in/service/v1/community/{community_id}/medias/live/end"
        return await self._send_request(url, params=params, headers=self.headers)

class Notify(BerrizAPIClient):
    async def fetch_notify(
        self, community_id: str, page_size: str,
        language_code: str, use_proxy: bool,
    ) -> Optional[Dict]:
        params = {"languageCode": language_code, "communityId": community_id, "pageSize": page_size,}

        url = "https://svc-api.berriz.in/service/v1/notifications"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        if response := await self._send_request(url, params=params, headers=headers, use_proxy=use_proxy):
            return response
        logger.warning(f"{Color.fg('bright_red')}Failed to obtain notification information{Color.reset()}")
        return None
    
class My(BerrizAPIClient):
    async def fetch_location(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}

        url = "https://svc-api.berriz.in/service/v1/my/geo-location"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        return await self._send_request(url, params=params, headers=headers)
    
    async def fetch_home(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}

        url = "https://svc-api.berriz.in/service/v1/home"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        return await self._send_request(url, params=params, headers=headers)

    async def fetch_my(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}

        url = "https://svc-api.berriz.in/service/v1/my"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        return await self._send_request(url, params=params, headers=headers)
    
    async def notifications(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}

        url = "https://svc-api.berriz.in/service/v1/notifications:new"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        return await self._send_request(url, params=params, headers=headers)
    
    async def fetch_me(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}
        url = "https://account.berriz.in/auth/v1/accounts"

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; iPhone18.3.2; iPhone14,8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'account.berriz.in',
        }
        return await self._send_request(url, params=params, headers=headers)

    async def fetch_fanclub(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}

        url = "https://svc-api.berriz.in/service/v1/fanclub/products/subscription"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        return await self._send_request(url, params=params, headers=headers)

class Community(BerrizAPIClient):
    async def community_keys(self) -> Optional[Dict]:
        params =  {"languageCode": 'en'}

        url = "https://svc-api.berriz.in/service/v1/community/keys"

        headers = {
            **self.headers,
            "Accept": "application/json",
        }
        return await self._send_request(url, params=params, headers=headers)
    
class MediaList(BerrizAPIClient):
    async def media_list(self, community_id, params) -> Optional[Dict]:
        
        url = f"https://svc-api.berriz.in/service/v1/community/{community_id}/medias/recent"
        
        return await self._send_request(url, params=params, headers=self.headers)

class GetRequest(BerrizAPIClient):
    async def get_request(self, url) -> Optional[Dict]:
        headers = {
            'User-Agent': 'Amazon CloudFront',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
        }
        return await self._send_request_http1(url, headers=headers, usecookie=False)