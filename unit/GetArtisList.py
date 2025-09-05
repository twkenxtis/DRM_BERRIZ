import asyncio
import logging
import os
import aiohttp
from typing import Dict, Optional
from aiohttp import ClientTimeout
from logging.handlers import TimedRotatingFileHandler

import aiohttp

from typing import Any, Dict, List, Optional, Tuple, Union


from unit.user_choice import NumericSelector


MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter( 
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger("GetArtisList")
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
        filename="logs/GetArtisList.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


logger = setup_logging()


class HeaderBuilder:
    @staticmethod
    def build_headers() -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": "https://berriz.in/",
            "Origin": "https://berriz.in",
            "Alt-Used": "svc-api.berriz.in",
        }


class ApiClient:
    def __init__(
        self,
        headers: Dict[str, str],
        delay: float = 0,
        max_connections: int = 10,
    ):
        self.base_url = "https://svc-api.berriz.in/service/v2"
        self.headers = headers
        self.delay = delay
        self.session: Optional[aiohttp.ClientSession] = None
        self.max_connections = max_connections

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=self.max_connections,
            force_close=False,
            enable_cleanup_closed=True,
            use_dns_cache=True,
            keepalive_timeout=13,
            ssl=True,
        )

        self.session = aiohttp.ClientSession(
            headers=self.headers,
            connector=connector,
            timeout=ClientTimeout(total=11),
            auto_decompress=True,
            json_serialize=lambda x: x,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    async def fetch_page(self, community_id: int, cursor: Optional[str], artis_id) -> Optional[Dict[str, Any]]:
        url = self._build_url(community_id, artis_id)
        params = self._build_params(cursor)
        return await self._request_json(url, params)

    def _build_url(self, community_id: int, artis_id: int) -> str:
        return f"{self.base_url}/community/{community_id}/artist/{artis_id}/archive"

    def _build_params(self, cursor: Optional[str]) -> Dict[str, Any]:
        params = {"pageSize": 999, "languageCode": "en"}
        if cursor:
            params["next"] = cursor
        return params

    async def _request_json(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assert self.session is not None, "ClientSession not initialized. Use `async with`."
        try:
            async with self.session.get(url, params=params, timeout=3) as response:
                logger.info(f"GET %s -> %s {response.request_info.real_url} \n {response.status}")
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            self._handle_request_error(e, url, params)
            return None

    def _handle_request_error(self, e: Exception, url: str, params: Dict[str, Any]) -> None:
        if isinstance(e, asyncio.TimeoutError):
            logger.error(f"Request timed out: {url} params={params}")
        elif isinstance(e, aiohttp.ClientResponseError):
            logger.error(f"HTTP {e.status} error on {url}: {e.message} params={params}")
        elif isinstance(e, aiohttp.ClientError):
            logger.error(f"Client error on {url}: {e} params={params}")
        else:
            logger.error(f"Unexpected error on {url}: {e}", exc_info=True)


class MediaParser:
    @staticmethod
    def parse(data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], Optional[str], bool]:
        if not MediaParser._is_valid_response(data):
            return [], [], None, False

        contents = MediaParser._get_contents(data)
        CMT_list, POST_list = MediaParser._extract_media_items(contents)
        cursor, has_next = MediaParser._extract_pagination(data)

        return CMT_list, POST_list, cursor, has_next

    @staticmethod
    def _is_valid_response(data: Dict[str, Any]) -> bool:
        code = data.get("code")
        if code != "0000":
            logger.warning(f"API error: {code}")
            return False
        return True

    @staticmethod
    def _get_contents(data: Dict[str, Any]) -> List[Dict]:
        return data.get("data", {}).get("contents", [])

    @staticmethod
    def _extract_media_items(contents: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        CMT_list, POST_list = [], []
        for item in contents:
            match item.get("contentType"):
                case "CMT":
                    CMT_list.append(item)
                case "POST":
                    POST_list.append(item)
        return CMT_list, POST_list

    @staticmethod
    def _extract_pagination(data: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        pagination = data.get("data", {})
        cursor = pagination.get("cursor", {}).get("next")
        has_next = pagination.get("hasNext", False)
        return cursor, has_next


class MediaFetcher:
    def __init__(self, community_id: int):
        self.community_id = community_id
        self.headers = HeaderBuilder.build_headers()
        
    async def get_all_media_lists(self) -> Tuple[List[Dict], List[Dict]]:
        cursor = None

        async with ApiClient(self.headers) as client:
            while True:
                data = await client.fetch_page(self.community_id, cursor)
                if not data:
                    break

                CMT_list, POST_list, cursor, has_next = MediaParser.parse(data)

                if not has_next:
                    break
                await asyncio.sleep(client.delay)

        return CMT_list, POST_list