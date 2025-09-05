import logging
import os
import re
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Union

import httpx

from cookies.cookies import Berriz_cookie
from static.PlaybackInfo import PlaybackInfo
from static.PublicInfo import PublicInfo


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("request_berriz_api")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "request_berriz_api.py.log"),
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


UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class BerrizAPIClient:

    def __init__(self):
        self.cookies = Berriz_cookie()._cookies
        self.headers = self._build_headers()

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Host": "svc-api.berriz.in",
            "Referer": "https://berriz.in/",
            "Accept": "application/json",
            'pragma': 'no-cache',
            "Origin": "https://berriz.in",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; iPhone17.6.1; fanz-ios 1.1.4; iPhone12,3",
        }

    async def _send_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:

        try:
            async with httpx.AsyncClient(http2=True, timeout=4, verify=False) as client:
                response = await client.get(
                    url,
                    params=params,
                    cookies=self.cookies,
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
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
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/playback_info"
                if data := await self._send_request(url):
                    results.append(data)
        return results


class Public_context(BerrizAPIClient):

    async def get_public_context(self, media_ids: Union[str, List[str]]) -> List[str]:
        media_ids = [media_ids] if isinstance(media_ids, str) else media_ids
        results = []
        for media_id in media_ids:
            if isinstance(media_id, str) and UUID_REGEX.match(media_id):
                url = f"https://svc-api.berriz.in/service/v1/medias/{media_id}/public_context"
                if data := await self._send_request(url):
                    results.append(data)
        return results