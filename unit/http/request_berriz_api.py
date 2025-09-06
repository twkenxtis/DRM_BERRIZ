import concurrent.futures
import logging
import os
import re
import threading
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Union

import httpx

from cookies.cookies import Berriz_cookie
from static.color import Color
from static.PlaybackInfo import PlaybackInfo
from static.PublicInfo import PublicInfo


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