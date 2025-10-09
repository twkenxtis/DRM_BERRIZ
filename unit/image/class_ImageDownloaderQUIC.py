import asyncio
from typing import Union, Dict, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import ssl


from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration


from static.color import Color
from lib.path import Path
from unit.http.quic import HttpClient, QuicResponse
from unit.handle.handle_log import setup_logging
from unit.__init__ import USERAGENT


logger = setup_logging('class_ImageDownloader', 'sienna')


class QuicSession:
    def __init__(self, default_headers: Optional[Dict[str, str]] = None):
        self.host = "statics.berriz.in"
        self._client = None
        self._context_manager = None
        self.default_headers = default_headers or {'user-agent': 'curl/7.64.1'}
        self.config = QuicConfiguration(
            is_client=True, 
            alpn_protocols=["h3"], 
            verify_mode=ssl.CERT_NONE
        )
    
    async def __aenter__(self):
        self._context_manager = connect(
            self.host, 443, 
            configuration=self.config, 
            create_protocol=HttpClient
        )
        self._client = await self._context_manager.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        if self._context_manager:
            await self._context_manager.__aexit__(*args)
    
    async def get(self, url: str, headers: Optional[Dict[str, str]] = None):
        merged_headers = {**self.default_headers, **(headers or {})}
        return await self._client.get(url, headers=merged_headers)


class QuicHTTPError(Exception):
    """QUIC HTTP 錯誤"""
    pass


class ImageDownloader:
    """Handles downloading images from URLs using aioquic with thread pool for file I/O."""
    
    @staticmethod
    def get_header() -> Dict[str, str]:
        return {
            "user-agent": f"{USERAGENT}",
            "accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,image/svg+xml,*/*",
        }

    _headers: Dict[str, str] = get_header()
    _file_io_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    @staticmethod
    async def _download_single(
        url: str,
        file_path: Union[str, Path],
        session: QuicSession
    ) -> bool:
        """執行單個圖片下載（內部方法）"""
        for attempt in range(7, 14):
            try:
                events = await session.get(url)
                resp = QuicResponse(url, events)
                resp.parse()
                
                logger.info(f"{Color.fg('light_gray')}{url}{Color.reset()} - {Color.fg('graphite')}{resp.status}{Color.reset()}")
                
                if resp.status != "200":
                    raise QuicHTTPError(f"HTTP {resp.status}")
                
                logger.info(f"{Color.fg('periwinkle')}{file_path}{Color.reset()}")
                
                # Write file
                path = Path(file_path)
                path.parent.mkdirp()
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    ImageDownloader._file_io_executor,
                    path.write_bytes,
                    resp.body
                )
                return True
                
            except QuicHTTPError as e:
                logger.warning(f"[Network Attempt {attempt}/10] Failed to download {url}: {e}")
                if attempt == 10:
                    logger.error(f"{url} download failed after 10 attempts")
                    return False
                await asyncio.sleep(0.25 * attempt)
            
            except (OSError, IOError) as e:
                logger.warning(f"File I/O error for {url} -> {file_path}: {e}")
                return False
                
            except asyncio.CancelledError:
                logger.warning(f"Download cancelled for {Color.fg('light_gray')}{url}{Color.reset()}")
                path = Path(file_path)
                if path.exists():
                    path.unlink()
                    logger.info(f"Removed partial file: {file_path}")
                raise
        return False

    @staticmethod
    @asynccontextmanager
    async def session_scope():
        """Context manager for managing session lifecycle."""
        session = QuicSession(default_headers=ImageDownloader._headers)
        try:
            await session.__aenter__()
            yield session
        finally:
            await session.__aexit__(None, None, None)

    @staticmethod
    async def download_image(url: str, file_path: Union[str, Path]) -> bool:
        """下載單個圖片（自動管理 session）"""
        async with ImageDownloader.session_scope() as session:
            return await ImageDownloader._download_single(url, file_path, session)

    @staticmethod
    async def download_images(
        downloads: List[Tuple[str, Union[str, Path]]]
    ) -> List[bool]:
        """批次下載多個圖片（共享單一 session）
        
        Args:
            downloads: List of (url, file_path) tuples
            
        Returns:
            List of bool indicating success/failure for each download
        """
        async with ImageDownloader.session_scope() as session:
            tasks = [
                ImageDownloader._download_single(url, path, session)
                for url, path in downloads
            ]
            return await asyncio.gather(*tasks)

    @classmethod
    def shutdown_executor(cls) -> None:
        """Shutdown the thread pool executor gracefully."""
        cls._file_io_executor.shutdown(wait=True)
        logger.info("File I/O executor shutdown complete")
