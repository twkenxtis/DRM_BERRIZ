import asyncio
import concurrent.futures
import logging
import random
import os
import re
import sys
import uuid
import threading
from functools import lru_cache
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Union, Any

import httpx

from lib.lock_cookie import cookie_session, Lock_Cookie
from static.api_error_handle import api_error_handle
from static.color import Color
from static.parameter import paramstore
from unit.__init__ import USERAGENT
from unit.handle.handle_log import ColoredConsoleFormatter



class NonBlockingFileHandler(TimedRotatingFileHandler):
    """使用線程池執行器實現非阻塞寫入"""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._executor: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="log_writer"
        )
        self._lock: threading.Lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """在線程池中執行文件寫入"""
        try:
            msg: str = self.format(record)
            # 在線程池中執行寫入操作（非阻塞）
            self._executor.submit(self._sync_write, msg)
        except Exception as e:
            print(f"Log transmission error: {e}")

    def _sync_write(self, message: str) -> None:
        """同步寫入方法（在線程中執行）"""
        try:
            with self._lock:
                with open(self.baseFilename, 'a', encoding=self.encoding) as f:
                    f.write(message + '\n')
        except Exception as e:
            print(f"File write error: {e}")

    def close(self) -> None:
        """關閉處理器"""
        try:
            self._executor.shutdown(wait=True)
        except Exception:
            pass
        super().close()


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory: str = "logs"
    os.makedirs(log_directory, exist_ok=True)
    
    console_format: ColoredConsoleFormatter = ColoredConsoleFormatter()

    # 文件格式（去除所有顏色代碼）
    class NoColorFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            message: str = super().format(record)
            # 移除所有顏色代碼
            color_pattern: str = r'(\033\[[0-9;]*m|Color\.\w+\([^)]*\)|Color\.reset\(\))'
            return re.sub(color_pattern, '', message)

    file_format: logging.Formatter = NoColorFormatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    log_level: int = logging.INFO

    app_logger: logging.Logger = logging.getLogger("request_berriz_api")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setFormatter(console_format)

    # 使用非阻塞文件處理器
    app_file_handler: NonBlockingFileHandler = NonBlockingFileHandler(
        filename=os.path.join(log_directory, "request_berriz_api.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(file_format)

    httpx_file_handler: NonBlockingFileHandler = NonBlockingFileHandler(
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
        lib_logger: logging.Logger = logging.getLogger(logger_name)
        lib_logger.setLevel(logging.INFO)
        
        if lib_logger.hasHandlers():
            lib_logger.handlers.clear()
        
        lib_logger.addHandler(console_handler)
        lib_logger.addHandler(httpx_file_handler)
        
        lib_logger.propagate = False

    return app_logger


logger: logging.Logger = setup_logging()



def is_valid_uuid(uuid_str: str) -> bool:
    """Check if string is a valid UUID."""
    try:
        uuid.UUID(uuid_str)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


base_sleep: float = 0.5
max_sleep: float = 5.0
max_retries: int = 5
retry_http_status: set[int] = frozenset({400, 401, 500, 502, 503, 504})


class BerrizAPIClient:
    
    _re_request_cookie: bool = True
    
    def __init__(self) -> None:
        self.headers: Dict[str, str] = self._build_headers()

    @lru_cache(maxsize=1)
    def _build_headers(self) -> Dict[str, str]:
        return {
            "Host": "svc-api.berriz.in",
            "Referer": "https://berriz.in/",
            "Origin": "https://berriz.in",
            "Accept": "application/json",
            'pragma': 'no-cache',
            "User-Agent": f"{USERAGENT}"
            }

    async def ensure_cookie(self) -> Dict[str, str]:
        max_retries: int = 5
        for _ in range(max_retries):
            cookie: Optional[Dict[str, str]] = await Lock_Cookie.cookie_session()
            if cookie not in (None, {}):
                return cookie
        raise RuntimeError("Fail to get cookie")
    
    async def cookie(self) -> Dict[str, str]:
        if paramstore.get('no_cookie') is not True:
            if cookie_session in (None, {}):
                BerrizAPIClient._re_request_cookie = False
                cookie: Dict[str, str] = await self.ensure_cookie()
                return cookie
            else:
                return cookie_session
        elif paramstore.get('no_cookie') is True:
            return {}

    async def _send_request(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        ck: Dict[str, str] = await self.cookie()
        if paramstore.get('no_cookie') is not True and ck in (None, {}):
            raise RuntimeError('Cookie is empty! cancel request')
        async with httpx.AsyncClient(http2=True, timeout=4, verify=True) as client:
            attempt: int = 0
            while attempt < max_retries:
                try:
                    response: httpx.Response = await client.get(
                        url,
                        params=params,
                        cookies = ck,
                        headers=headers or self.headers,
                    )
                    if response.status_code in retry_http_status:
                        raise httpx.HTTPStatusError(
                            f"Retryable server error: {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response.json()
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning(f"Network exception, retry {attempt + 1}/{max_retries}: {e}")
                except httpx.HTTPStatusError as e:
                    if e.response is not None and e.response.status_code in retry_http_status:
                        logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{max_retries}")
                    else:
                        logger.error(f"HTTP error for {url}: {e}")
                        return None
                attempt += 1
                sleep: float = min(max_sleep, base_sleep * (2 ** attempt))
                sleep *= (0.5 + random.random())
                await asyncio.sleep(sleep)
        logger.error(f"Retry exceeded for {url}")
        return None
            
    async def _patch_request(self, url: str, json_data: Dict[str, Any], params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        ck: Dict[str, str] = await self.cookie()
        if paramstore.get('no_cookie') is not True and ck in (None, {}):
            raise RuntimeError('Cookie is empty! cancel request')
        try:
            async with httpx.AsyncClient(http2=True, timeout=4, verify=True) as client:
                response: httpx.Response = await client.patch(
                    url,
                    params=params,
                    cookies = ck,
                    headers=headers or self.headers,
                    json=json_data,
                )
                if response.status_code not in range(200, 300):
                    logger.error(f"HTTP error for {url}: {response.status_code}")
                    return None
                return response.json()
        except httpx.ConnectTimeout:
            logger.warning(f"{Color.fg('light_gray')}Request timeout:{Color.reset()} {Color.fg('periwinkle')}{url}{Color.reset()}")

    async def _send_post(self, url: str, json_data: Dict[str, Any], params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        ck: Dict[str, str] = await self.cookie()
        if paramstore.get('no_cookie') is not True and ck in (None, {}):
            raise RuntimeError('Cookie is empty! cancel request')
        async with httpx.AsyncClient(http2=True, timeout=3, verify=True) as client:
            attempt: int = 0
            while attempt < max_retries:
                try:
                    response: httpx.Response = await client.post(
                        url,
                        params=params,
                        cookies=ck,
                        headers=headers or self.headers,
                        json=json_data,
                    )
                    if response.status_code in retry_http_status:
                        raise httpx.HTTPStatusError(
                            f"Retryable server error: {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response.json()
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning(f"Network exception, retry {attempt + 1}/{max_retries}: {e}")
                except httpx.HTTPStatusError as e:
                    if e.response is not None and e.response.status_code in retry_http_status:
                        logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{max_retries}")
                    else:
                        logger.error(f"HTTP error for {url}: {e}")
                        return None
                attempt += 1
                sleep: float = min(max_sleep, base_sleep * (2 ** attempt))
                sleep *= (0.5 + random.random())
                await asyncio.sleep(sleep)
        logger.error(f"Retry exceeded for {url}")
        return None

    async def _send_options(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        ck: Dict[str, str] = await self.cookie()
        if paramstore.get('no_cookie') is not True and ck in (None, {}):
            raise RuntimeError('Cookie is empty! cancel request')
        try:
            async with httpx.AsyncClient(http2=True, timeout=3, verify=True) as client:
                response: httpx.Response = await client.post(
                    url,
                    params=params,
                    cookies = ck,
                    headers=headers or self.headers,
                )
                if response.status_code not in range(200, 300):
                    logger.error(f"HTTP error for {url}: {response.status_code}")
                    return None
            if response.status_code not in range(200, 300):
                logger.error(f"HTTP error for {url}: {response.status_code}")
                return None
            return response.json()
        except httpx.ConnectTimeout:
            logger.warning(f"{Color.fg('light_gray')}Request timeout:{Color.reset()} {Color.fg('periwinkle')}{url}{Color.reset()}")

    async def _send_request_http1(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, usecookie: bool = False) -> Optional[httpx.Response]:
        ck: Dict[str, str] = await self.cookie()
        if paramstore.get('no_cookie') is not True and ck in (None, {}):
            raise RuntimeError('Cookie is empty! cancel request')
        c: Dict[str, str]
        if usecookie is False:
            c = {}
        else:
            c = ck
        attempt: int = 0
        while attempt < max_retries:
            async with httpx.AsyncClient(http2=False, timeout=4, verify=True) as client:
                try:
                    response: httpx.Response = await client.get(
                        url,
                        params=params,
                        cookies=c,
                        headers=headers or self.headers,
                    )
                    # 可選：對 5xx 進行重試
                    if response.status_code in retry_http_status:
                        raise httpx.HTTPStatusError(
                            f"Retryable server error: {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning(f"Network exception, retry {attempt + 1}/{max_retries}: {e}")
                except httpx.HTTPStatusError as e:
                    # 預設：非 2xx 直接返回；若屬於可重試的 5xx，已在上方轉成 HTTPStatusError 進入此處
                    if e.response is not None and e.response.status_code in retry_http_status:
                        logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{max_retries}")
                    else:
                        logger.error(f"HTTP error for {url}: {e}")
                        return None
                attempt += 1
                sleep: float = min(max_sleep, base_sleep * (2 ** attempt))
                sleep *= (0.5 + random.random())
                await asyncio.sleep(sleep)
        logger.error(f"Retry exceeded for {url}")
        return None

class Playback_info(BerrizAPIClient):
    async def get_playback_context(self, media_ids: Union[str, List[str]]) -> List[Dict[str, Any]]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results: List[Dict[str, Any]] = []
        for media_id in media_ids:
            if isinstance(media_id, str) and is_valid_uuid(media_id):
                params: Dict[str, str] = {"languageCode": 'en'}
                url: str = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/playback_info"
                if data := await self._send_request(url, params):
                    results.append(data)
            else:
                logger.warning(f"Invalid media ID format: {media_id}")
        return results

    async def get_live_playback_info(self, media_ids: Union[str, List[str]]) -> List[Dict[str, Any]]:
        """Fetch playback information for given media IDs."""
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results: List[Dict[str, Any]] = []
        for media_id in media_ids:
            if isinstance(media_id, str) and is_valid_uuid(media_id):
                params: Dict[str, str] = {"languageCode": 'en'}
                url: str = f"https://svc-api.berriz.in/service/v1/medias/live/replay/{media_id}/playback_area_context"
                if data := await self._send_request(url, params):
                    results.append(data)
            else:
                logger.warning(f"Invalid media ID format: {media_id}")
        return results


class Public_context(BerrizAPIClient):
    async def get_public_context(self, media_ids: Union[str, List[str]]) -> List[Dict[str, Any]]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results: List[Dict[str, Any]] = []
        for media_id in media_ids:
            if isinstance(media_id, str) and is_valid_uuid(media_id):
                params: Dict[str, str] = {"languageCode": 'en'}
                url: str = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/public_context"
                if data := await self._send_request(url, params):
                    results.append(data)
            else:
                logger.warning(f"Invalid media ID format: {media_id}")
        return results


class Live(BerrizAPIClient):
    async def request_live_playlist(self, playback_url: str, media_id: str) -> Optional[str]:
        """Request m3u8 playlist."""
        if not playback_url:
            logger.error(
                f"{Color.fg('light_gray')}No playback URL provided for media_id{Color.reset()}:"
                f" {Color.fg('turquoise')}{media_id}{Color.reset()}"
            )
            return None

        headers: Dict[str, str] = {
            **self.headers,
            "Accept": "application/x-mpegURL, application/vnd.apple.mpegurl, application/json, text/plain",
            "Referer": "Berriz/20250704.1139 CFNetwork/1498.700.2 Darwin/23.6.0",
        }

        try:
            if response := await self._send_request(playback_url, headers):
                return response
        except httpx.HTTPError as e:
            logger.error(
                f"{Color.fg('plum')}Failed to get m3u8 list for media_id{Color.reset()}"
                f" {Color.fg('turquoise')}{media_id}{Color.reset()}{Color.fg('plum')}: {e}{Color.reset()}"
            )
            return None

    async def fetch_mpd(self, url: str) -> Optional[str]:
        return await self._send_request_http1(url, usecookie=False)

    async def fetch_statics(self) -> Optional[Dict[str, Any]]:
        """Fetch static media information for the given media sequence."""
        if self.media_seq is None:
            logger.error("Cannot fetch statics: media_seq is not provided.")
            return None
        url: str = (
            f"https://svc-api.berriz.in/service/v1/media/statics?"
            f"languageCode=en&mediaSeq={self.media_seq}&t=1"
        )
        d = await self._send_request(url)
        if d is not None: return d

    async def fetch_chat(self, current_second: int) -> Optional[Dict[str, Any]]:
        """Fetch chat data for the given media sequence and time."""
        if self.media_seq is None:
            logger.error("Cannot fetch chat: media_seq is not provided.")
            return None
        url: str = (
            f"https://chat-api.berriz.in/chat/v1/sync?"
            f"translateLanguageCode=en&mediaSeq={self.media_seq}&t={current_second}&languageCode=en"
        )
        headers: Dict[str, str] = {
            **self.headers,
            "Host": "chat-api.berriz.in",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        d = await self._send_request(url, headers)
        if d is not None: return d

    async def fetch_media_seq(self, media_url: str) -> Optional[int]:
        """Fetch mediaSeq from a media URL."""
        headers: Dict[str, str] = {
            **self.headers,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            if response := await self._send_request(media_url, headers):
                data: Dict[str, Any] = response.json()
            media_seq: Optional[int] = data.get("data", {}).get("media", {}).get("mediaSeq")
            if media_seq is None:
                logger.error("mediaSeq not found in response.")
            else:
                self.media_seq = media_seq  # Update instance media_seq
            return media_seq
        except (httpx.HTTPError, KeyError) as e:
            logger.error(f"Failed to fetch mediaSeq from {media_url}: {e}")
            return None

    async def fetch_live_replay(self, community_id: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url: str = f"https://svc-api.berriz.in/service/v1/community/{community_id}/medias/live/end"
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d


class Notify(BerrizAPIClient):
    async def fetch_notify(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url: str = "https://svc-api.berriz.in/service/v1/notifications"
        headers: Dict[str, str] = {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'svc-api.berriz.in',
            'Connection': 'keep-alive',
            'Sec-Fetch-Site': 'cross-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
        if response := await self._send_request(url, params, headers):
            return response
        logger.warning(f"{Color.fg('bright_red')}Failed to obtain notification information{Color.reset()}")
        return None


class My(BerrizAPIClient):
    async def fetch_location(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/my/geo-location"
        headers: Dict[str, str] = {**self.headers, "Accept": "application/json"}
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def fetch_home(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/home"
        headers: Dict[str, str] = {**self.headers, "Accept": "application/json"}
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def fetch_my(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/my"
        headers: Dict[str, str] = {**self.headers, "Accept": "application/json"}
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def notifications(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/notifications:new"
        headers: Dict[str, str] = {**self.headers, "Accept": "application/json"}
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def fetch_me(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://account.berriz.in/auth/v1/accounts"
        headers: Dict[str, str] = {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'account.berriz.in',
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def fetch_fanclub(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/fanclub/products/subscription"
        headers: Dict[str, str] = {**self.headers, "Accept": "application/json"}
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def get_me_info(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://account.berriz.in/member/v1/members/me"
        headers: Dict[str, str] = {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'account.berriz.in',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return d
    

class Community(BerrizAPIClient):
    async def community_keys(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}

        url: str = "https://svc-api.berriz.in/service/v1/community/keys"

        headers: Dict[str, str] = {
            **self.headers,
            "Accept": "application/json",
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return d

    async def community_menus(self, communityId: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        from unit.community import get_community
        if type(communityId) is not int:
            communityId = await get_community(communityId)
        if not isinstance(communityId, int):
            logger.error(f'{Color.fg('red')}communityId should be int {Color.reset()} Current is ⭢ {Color.bg('ruby')}{communityId}')
            sys.exit(0)

        url: str = f"https://svc-api.berriz.in/service/v1/community/info/{communityId}/menus"

        headers: Dict[str, str] = {
            **self.headers,
            "Accept": "application/json",
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return d
    
    async def community_name(self, communityId:int) -> Optional[Dict[str, Any]]:
        params = {'communityid': f'{communityId}', 'languageCode': 'en'}
        url = "https://svc-api.berriz.in/service/v1/my/state"
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d

    async def community_id(self, communityname:str) -> Optional[Dict[str, Any]]:
        params = {'languageCode': 'en'}
        url = f"https://svc-api.berriz.in/service/v1/community/id/{communityname}"
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d
        
    async def create_community(self, communityId: int, name: str) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        if type(communityId) is not int:
            raise ValueError(f'{communityId} should be int')
        if len(name) > 15:
            raise ValueError(f'{name} community name only accept length < 15')
        json_data: Dict[str, Any] = {
            'communityId': communityId,
            'name': name,
            'communityTermsIds': [],
        }
        url: str = 'https://svc-api.berriz.in/service/v1/community/user/create'
        d = await self._send_post(url, json_data, params, self.headers)
        if d is not None: return d
    
    async def leave_community(self, communityId: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, Union[int, str]] = {
            'communityId': communityId,
            'languageCode': 'en',
        }
        if type(communityId) is not int:
            raise ValueError(f'{communityId} should be int')
        url: str = 'https://svc-api.berriz.in/service/v1/community/user/withdraw'
        d = await self._send_post(url, json_data={}, params=params, headers=self.headers)
        if d is not None: return d

class MediaList(BerrizAPIClient):
    async def media_list(self, community_id: Union[int, str], params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url: str = f"https://svc-api.berriz.in/service/v1/community/{community_id}/medias/recent"
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d


class GetRequest(BerrizAPIClient):
    async def get_request(self, url: str) -> Optional[httpx.Response]:
        return await self._send_request_http1(url, usecookie=False)


_pw_re: re.Pattern = re.compile(
    r'^'  # Start of string
    r'(?=.*[A-Za-z])'  # At least one letter
    r'(?=.*\d)'  # At least one digit
    r'(?=.*[!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])'  # At least one special character
    r'[\x20-\x7E]{8,32}'  # Printable ASCII characters, length 8-32
    r'$'  # End of string
)

class Password_Change(BerrizAPIClient):
    def validate_password_regex(self, password: str) -> bool:
        return bool(_pw_re.match(password))

    async def update_password(self, currentPassword: str, newPassword: str) -> Optional[Dict[str, Any]]:
        if self.validate_password_regex(newPassword) and self.validate_password_regex(currentPassword) is False:
            logging.warning('Your password must contain 8 to 32 alphanumeric and special characters')
            raise ValueError('Invaild password formact')
        
        if self.validate_password_regex(newPassword) and self.validate_password_regex(currentPassword) is True:
            params: Dict[str, str] = {'languageCode': 'en'}
            json_data: Dict[str, str] = {
                'currentPassword': currentPassword,
                'newPassword': newPassword,
            }
            headers: Dict[str, str] = {
                'User-Agent': f"{USERAGENT}",
                'Accept': 'application/json',
                'Referer': 'https://berriz.in/',
                'Content-Type': 'application/json',
                'Origin': 'https://berriz.in',
                'Alt-Used': 'account.berriz.in',
                'Connection': 'keep-alive',
            }
            url: str = 'https://account.berriz.in/auth/v1/accounts:update-password'
            d = await self._patch_request(url, json_data, params, headers)
            if d is not None: return d
        return None

class Arits(BerrizAPIClient):
    def __init__(self) -> None:
        self.headers: Dict[str, str] = self.header()
        
    def header(self) -> Dict[str, str]:
        return {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'svc-api.berriz.in',
            'Connection': 'keep-alive',
        }
        
    async def artis_list(self, community_id: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/artists'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d

    async def _board_list(self, board_id: str, community_id: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/boards/{board_id}/feed'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d
    
    async def arits_archive(self, community_id: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, Union[str, int]] = {'languageCode': 'en', 'pageSize': 99}
        url: str = f'https://svc-api.berriz.in/service/v2/community/{community_id}/artist/archive'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d
    
    async def post_detil(self, community_id: int, post_uuid: str) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/post/{post_uuid}'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d

    async def request_notice(self, community_id: int, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/notices'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d

    async def request_notice_page(self, community_id: int, communityNoticeId: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/notices/{communityNoticeId}'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return d
    

class Translate(BerrizAPIClient):
    async def translate_post(self, post_id: str, target_lang: str) -> Optional[str]:
        if not post_id:
            logger.error("Text to translate cannot be empty.")
            return None
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/translate/post"
        json_data: Dict[str, str] = {
            'postId': post_id,
            'translateLanguageCode': target_lang,
        }
        headers: Dict[str, str] = {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'application/json',
        }
        data: Optional[Dict[str, Any]] = await self._send_post(url, json_data, params, headers)
        if data is None: # 處理 _send_post 回傳 None 的情況
            return None
        if data.get('code') != '0000':
            raise RuntimeError(f"Translation API error: {data.get('message', 'Unknown error')}")
        
        result: Optional[str] = data.get('data', {}).get('result')
        return result.strip() if result else None
