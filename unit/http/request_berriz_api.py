import asyncio
import logging
import random
import re
import uuid
from functools import lru_cache
from typing import Dict, List, Optional, Union, Any

import httpx

from cookies.cookies import Berriz_cookie
from lib.lock_cookie import cookie_session, Lock_Cookie
from static.api_error_handle import api_error_handle
from static.color import Color
from static.parameter import paramstore
from unit.__init__ import USERAGENT
from unit.handle.handle_log import setup_logging


logger = setup_logging('berriz_create_community', 'aluminum')



def is_valid_uuid(uuid_str: str) -> bool:
    """Check if string is a valid UUID."""
    try:
        uuid.UUID(uuid_str)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


base_sleep: float = 0.05
max_sleep: float = 1.0
max_retries: int = 7
retry_http_status: set[int] = frozenset({400, 401, 500, 502, 503, 504})


def handle_response(obj):
    raw_response = obj
    if obj is None:
        raise ValueError("response is None")
    try:
        logger.debug(f"Response: {raw_response}, {type(raw_response)}")
        match obj:
            case dict():
                TYPE = 'DICT'
                pass
            case list():
                TYPE = 'LIST'
                pass
            case str():
                return raw_response
            case object():
                TYPE = 'RESPONSE-OBJECT'
            case _:
                TYPE = ''   
        while True:
            try:
                if TYPE == 'LIST':
                    obj = obj[0]
                elif TYPE == 'RESPONSE-OBJECT':
                    if isinstance(obj, bytes):
                        return raw_response
                    if isinstance(obj, httpx.Response):
                        return raw_response
            except (TypeError, IndexError, KeyError):
                raise TypeError(f"Cannot unpack into dict: {obj!r}")
            
            if obj['code'] != "0000":
                logger.error(api_error_handle(obj['code']))
                raise ValueError(
                    f"Error code: {Color.bg('orange')}{obj['code']}{Color.reset()}{Color.fg('ruby')}"
                    f", message: {Color.fg('iron')}{obj['message']}{Color.reset()}"
                    )
            elif obj['code'] == "0000":
                return raw_response
    except Exception as e:
        logger.error(e)
        raise ValueError(e)


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
                    try:
                        response.json()
                        return response.json()
                    except ValueError:
                        return response.text
                
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning(f"Network exception, retry {attempt + 1}/{max_retries}: {e}")
                except httpx.HTTPStatusError as e:
                    match e.response.status_code:
                        case 401:
                            await Berriz_cookie.create_temp_json()
                            await Berriz_cookie().get_cookies()
                            return None
                        case _:
                            if e.response is not None and e.response.status_code in retry_http_status:
                                logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{max_retries}")
                            else:
                                logger.error(f"HTTP error for {url}: {e} {Color.bg('gold')}{response}{Color.reset()}")
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
                    logger.error(f"HTTP error for {url}: {Color.bg('gold')}{response}{Color.reset()}")
                    return None
                try:
                    response.json()
                    return response.json()
                except ValueError:
                    return response.text
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
                    try:
                        response.json()
                        return response.json()
                    except ValueError:
                        return response.text
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    logger.warning(f"Network exception, retry {attempt + 1}/{max_retries}: {e}")
                except httpx.HTTPStatusError as e:
                    match e.response.status_code:
                        case 401:
                            await Berriz_cookie.create_temp_json()
                            await Berriz_cookie().get_cookies()
                            return None
                        case _:
                            if e.response is not None and e.response.status_code in retry_http_status:
                                logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{max_retries}")
                            else:
                                logger.error(f"HTTP error for {url}: {e} {Color.bg('gold')}{response}{Color.reset()}")
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
                logger.error(f"HTTP error for {url}: {Color.bg('gold')}{response}{Color.reset()}")
                return None
            try:
                response.json()
                return response.json()
            except ValueError:
                return response.text
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
                    match e.response.status_code:
                        case 401:
                            await Berriz_cookie.create_temp_json()
                            await Berriz_cookie().get_cookies()
                            return None
                        case _:
                            if e.response is not None and e.response.status_code in retry_http_status:
                                logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{max_retries}")
                            else:
                                logger.error(f"HTTP error for {url}: {e} {Color.bg('gold')}{response}{Color.reset()}")
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
        return handle_response(results)

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
        return handle_response(results)


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
        return handle_response(results)


class Live(BerrizAPIClient):
    async def request_live_playlist(self, playback_url: str, media_id: str) -> Optional[str]:
        """Request m3u8 playlist."""
        if not playback_url:
            logger.error(
                f"{Color.fg('light_gray')}No playback URL provided for media_id{Color.reset()}:"
                f" {Color.fg('turquoise')}{media_id}{Color.reset()}"
            )
            return None
        params: Dict[str, str] = {"": ""}
        headers: Dict[str, str] = {
            "User-Agent": f"{USERAGENT}",
            "Accept": "application/x-mpegURL, application/vnd.apple.mpegurl, application/json, text/plain",
            "Referer": "Berriz/20250704.1139 CFNetwork/1498.700.2 Darwin/23.6.0",
        }
        try:
            if response := await self._send_request(playback_url, params, headers):
                return handle_response(response)
        except httpx.HTTPError as e:
            logger.error(
                f"{Color.fg('plum')}Failed to get m3u8 list for media_id{Color.reset()}"
                f" {Color.fg('turquoise')}{media_id}{Color.reset()}{Color.fg('plum')}: {e}{Color.reset()}"
            )
            return None

    async def fetch_mpd(self, url: str) -> Optional[str]:
        d = await self._send_request_http1(url, usecookie=False)
        if d is not None: return handle_response(d)

    async def fetch_statics(self, media_seq: int) -> Optional[Dict[str, Any]]:
        """Fetch static media information for the given media sequence."""
        try:
            if int(media_seq) is None:
                logger.error("Cannot fetch statics: media_seq is not provided.")
        except AttributeError:
            logger.error("Cannot fetch statics: media_seq is not provided.")
            raise ValueError('media_seq is None.')
        params: Dict[str, str] = {'languageCode': 'en', 'mediaSeq': f'{int(media_seq)}', 't': '1'}
        url: str = f"https://svc-api.berriz.in/service/v1/media/statics"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def fetch_chat(self, current_second: int, media_seq: int) -> Optional[Dict[str, Any]]:
        """Fetch chat data for the given media sequence and time."""
        if int(media_seq) is None:
            logger.error("Cannot fetch chat: media_seq is not provided.")
            return None
        params: Dict[str, str] = {'languageCode': 'en', 'translateLanguageCode': 'en', 'mediaSeq': f'{int(media_seq)}', 't': f'{current_second}'}
        url: str = f"https://chat-api.berriz.in/chat/v1/sync"
        headers: Dict[str, str] = {
            **self.headers,
            "Host": "chat-api.berriz.in",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return handle_response(d)

    async def fetch_live_replay(self, community_id: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        Community_id_checker(community_id)
        url: str = f"https://svc-api.berriz.in/service/v1/community/{community_id}/medias/live/end"
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)


class Notify(BerrizAPIClient):
    async def fetch_notify(
        self, community_id: str, page_size: str, language_code: str) -> Optional[Dict]:
        if community_id == '':
            params: Dict[str, str] = {"languageCode": language_code, "pageSize": page_size}
        else:
            params: Dict[str, str] = {"languageCode": language_code, "communityId": community_id, "pageSize": page_size}

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
            return handle_response(response)
        logger.warning(f"{Color.fg('bright_red')}Failed to obtain notification information{Color.reset()}")
        return None


class My(BerrizAPIClient):
    async def fetch_location(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/my/geo-location"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def fetch_home(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/home"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def fetch_my(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/my"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def notifications(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/notifications:new"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def fetch_me(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://account.berriz.in/auth/v1/accounts"
        headers: Dict[str, str] = {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'account.berriz.in',
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return handle_response(d)

    async def fetch_fanclub(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/fanclub/products/subscription"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def get_me_info(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        url: str = "https://account.berriz.in/member/v1/members/me"
        headers: Dict[str, str] = {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'account.berriz.in',
            'Connection': 'keep-alive',
        }
        d = await self._send_request(url, params, headers)
        if d is not None: return handle_response(d)
    

class Community(BerrizAPIClient):
    async def community_keys(self) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'ko'}
        url: str = "https://svc-api.berriz.in/service/v1/community/keys"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def community_menus(self, communityId: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        Community_id_checker(communityId)
        url: str = f"https://svc-api.berriz.in/service/v1/community/info/{communityId}/menus"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)
    
    async def community_name(self) -> Optional[Dict[str, Any]]:
        params = {'languageCode': 'en'}
        url = "https://svc-api.berriz.in/service/v1/my/state"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)

    async def community_id(self, communityname:str) -> Optional[Dict[str, Any]]:
        params = {'languageCode': 'en'}
        url = f"https://svc-api.berriz.in/service/v1/community/id/{communityname}"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)
        
    async def create_community(self, communityId: int, name: str) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"languageCode": 'en'}
        Community_id_checker(communityId)
        json_data: Dict[str, Any] = {
            'communityId': communityId,
            'name': name,
            'communityTermsIds': [],
        }
        url: str = 'https://svc-api.berriz.in/service/v1/community/user/create'
        d = await self._send_post(url, json_data, params)
        if d is not None: return handle_response(d)
    
    async def leave_community(self, communityId: int) -> Optional[Dict[str, Any]]:
        params: Dict[str, Union[int, str]] = {'communityId': communityId, 'languageCode': 'en'}
        Community_id_checker(communityId)
        url: str = 'https://svc-api.berriz.in/service/v1/community/user/withdraw'
        d = await self._send_post(url, json_data={}, params=params, headers=self.headers)
        if d is not None: return handle_response(d)

class MediaList(BerrizAPIClient):
    async def media_list(self, community_id: Union[int, str], params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        Community_id_checker(community_id)
        url: str = f"https://svc-api.berriz.in/service/v1/community/{community_id}/medias/recent"
        d = await self._send_request(url, params)
        if d is not None: return handle_response(d)


class GetRequest(BerrizAPIClient):
    async def get_request(self, url: str) -> Optional[httpx.Response]:
        d = await self._send_request_http1(url, usecookie=False)
        if d is not None: return handle_response(d)


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
            if d is not None: return handle_response(d)
        return None

class Arits(BerrizAPIClient):
    def __init__(self) -> None:
        self.headers: Dict[str, str] = self.header()
        self.community_id_checker = Community_id_checker
        
    def header(self) -> Dict[str, str]:
        return {
            'User-Agent': f"{USERAGENT}",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Alt-Used': 'svc-api.berriz.in',
            'Connection': 'keep-alive',
        }
        
    async def artis_list(self, community_id: int) -> Optional[Dict[str, Any]]:
        self.community_id_checker(community_id)
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/artists'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)

    async def _board_list(self, board_id: str, community_id: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.community_id_checker(community_id)
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/boards/{board_id}/feed'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)
    
    async def arits_archive(self, community_id: int) -> Optional[Dict[str, Any]]:
        self.community_id_checker(community_id)
        params: Dict[str, Union[str, int]] = {'languageCode': 'en', 'pageSize': 99}
        url: str = f'https://svc-api.berriz.in/service/v2/community/{community_id}/artist/archive'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)
    
    async def post_detil(self, community_id: int, post_uuid: str) -> Optional[Dict[str, Any]]:
        self.community_id_checker(community_id)
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/post/{post_uuid}'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)

    async def request_notice(self, community_id: int, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.community_id_checker(community_id)
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/notices'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)

    async def request_notice_page(self, community_id: int, communityNoticeId: int) -> Optional[Dict[str, Any]]:
        self.community_id_checker(community_id)
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = f'https://svc-api.berriz.in/service/v1/community/{community_id}/notices/{communityNoticeId}'
        d = await self._send_request(url, params, self.headers)
        if d is not None: return handle_response(d)
    

class Translate(BerrizAPIClient):
    async def translate_post(self, post_id: uuid, target_lang: str) -> Optional[str]:
        if not post_id:
            logger.error("Text to translate cannot be empty.")
            return None
        params: Dict[str, str] = {'languageCode': 'en'}
        url: str = "https://svc-api.berriz.in/service/v1/translate/post"
        json_data: Dict[str, str] = {
            'postId': post_id,
            'translateLanguageCode': target_lang,
        }
        data: Optional[Dict[str, Any]] = await self._send_post(url, json_data, params)
        if data is None: # 處理 _send_post 回傳 None 的情況
            return None
        result: Optional[str] = data.get('data', {}).get('result')
        return handle_response(result) if result else None


class Community_id_checker:
    def __init__(self, community_id: Union[int, str]) -> None:
        self.input = community_id
        self.check_community_id()
        
    def check_community_id(self) -> None:
        try:
            communityId = int(self.input)
            if not isinstance(communityId, int):
                raise ValueError
        except ValueError:
            logger.error(f'{Color.fg('red')}communityId should be int {Color.reset()} Current is ⭢　{Color.bg('ruby')}{self.input}')
            raise ValueError(f'Value {Color.bg('ruby')}{self.input}{Color.reset()} should be int')

            