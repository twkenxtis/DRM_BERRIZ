import asyncio
import os
import aiohttp
import logging
from typing import Dict, Any, Optional, Tuple, List, Union
from logging.handlers import TimedRotatingFileHandler

from unit.user_choice import NumericSelector


MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]


def setup_logging() -> logging.Logger:
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("GetMediaList")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "GetMediaList.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)
    return app_logger


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
    def __init__(self, headers: Dict[str, str], delay: float = 0.5):
        self.base_url = "https://svc-api.berriz.in/service/v1"
        self.headers = headers
        self.delay = delay
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_page(self, community_id: int, cursor: Optional[str]) -> Optional[Dict[str, Any]]:
        url = self._build_url(community_id)
        params = self._build_params(cursor)
        return await self._request_json(url, params)

    def _build_url(self, community_id: int) -> str:
        return f"{self.base_url}/community/{community_id}/mediaCategories/112/medias"

    def _build_params(self, cursor: Optional[str]) -> Dict[str, Any]:
        params = {"pageSize": 20, "languageCode": "en"}
        if cursor:
            params["cursor"] = cursor
        return params

    async def _request_json(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assert self.session is not None, "ClientSession not initialized. Use `async with`."
        try:
            async with self.session.get(url, params=params, timeout=3) as response:
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
        vod_list, photo_list = MediaParser._extract_media_items(contents)
        cursor, has_next = MediaParser._extract_pagination(data)

        return vod_list, photo_list, cursor, has_next

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
        vod_list, photo_list = [], []
        for item in contents:
            media = item.get("media")
            if not media:
                continue
            match media.get("mediaType"):
                case "VOD":
                    vod_list.append(media)
                case "PHOTO":
                    photo_list.append(media)
        return vod_list, photo_list

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
        vod_total, photo_total = [], []
        cursor = None

        async with ApiClient(self.headers) as client:
            while True:
                data = await client.fetch_page(self.community_id, cursor)
                if not data:
                    break

                vods, photos, cursor, has_next = MediaParser.parse(data)
                vod_total.extend(vods)
                photo_total.extend(photos)

                if not has_next:
                    break
                await asyncio.sleep(client.delay)

        return vod_total, photo_total


async def handle_choice():
    community_id = 7

    media_fetcher = MediaFetcher(community_id=community_id)
    vod_list, photo_list = await media_fetcher.get_all_media_lists()

    if not vod_list and not photo_list:
        logger.warning("No media items found")
        return None

    selector = NumericSelector(vod_list, photo_list, page_size=60)
    selected_media = selector.run()

    print(f"- {len(selected_media['vods'])} 個 VOD")
    print(selected_media['vods'])
    print(type(selected_media['vods']))
    print(len(selected_media['vods']))
    print(f"- {len(selected_media['photos'])} 張照片")
    print(selected_media['photos'])

    return selected_media


if __name__ == "__main__":
    try:
        final_selection = asyncio.run(handle_choice())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"主程式執行錯誤: {e}", exc_info=True)