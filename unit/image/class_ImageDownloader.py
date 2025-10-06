import asyncio
from pathlib import Path
from typing import Union, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

import aiohttp

from static.color import Color
from unit.handle.handle_log import setup_logging
from unit.__init__ import USERAGENT


logger = setup_logging('class_ImageDownloader', 'sienna')


class ImageDownloader:
    """Handles downloading images from URLs using aiohttp with thread pool for file I/O."""

    @staticmethod
    def get_header() -> Dict[str, str]:
        return {
            "User-Agent": f"{USERAGENT}",
            "Cache-Control": "no-cache",
            "Accept-Encoding": "identity",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,image/svg+xml,*/*",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "image",
        }

    _headers: Dict[str, str] = get_header.__func__()
    _timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
        total=30.0,
        connect=13.0,
    )
    _connector_limit: int = 50
    _file_io_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    @staticmethod
    def _write_chunks_sync(chunks: list[bytes], file_path: Path) -> None:
        """Synchronous function to write chunks to file in thread pool."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            for chunk in chunks:
                f.write(chunk)

    @staticmethod
    async def _write_to_file(
        response: aiohttp.ClientResponse, 
        file_path: Union[str, Path]
    ) -> None:
        """Stream response content and offload file writing to thread pool."""
        path = Path(file_path)
        chunks: list[bytes] = []
        
        try:
            # Collect all chunks in memory first
            async for chunk in response.content.iter_chunked(10240):
                chunks.append(chunk)
            
            # Offload blocking file I/O to thread pool
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                ImageDownloader._file_io_executor,
                ImageDownloader._write_chunks_sync,
                chunks,
                path
            )
            
        except asyncio.CancelledError:
            # Clean up partial file on cancellation
            if path.exists():
                path.unlink()
                logger.info(f"Removed partial file: {path}")
            raise

    @staticmethod
    async def download_image(
        url: str, 
        file_path: Union[str, Path],
        session: Optional[aiohttp.ClientSession] = None
    ) -> bool:
        """Download image with retry logic.
        
        Args:
            url: Image URL to download
            file_path: Destination file path
            session: Optional existing ClientSession to reuse
            
        Returns:
            True if download successful, False otherwise
        """
        async def _download_with_session(sess: aiohttp.ClientSession) -> bool:
            for attempt in range(1, 11):
                try:
                    async with sess.get(url) as resp:
                        logger.info(f"{Color.fg('light_gray')}{url}{Color.reset()} - {Color.fg('graphite')}{resp.status}{Color.reset()}")
                        resp.raise_for_status()
                        logger.info(f"{Color.fg('periwinkle')}{file_path}{Color.reset()}")
                        await ImageDownloader._write_to_file(resp, file_path)
                    return True
                    
                except (aiohttp.ClientError, aiohttp.http_exceptions.HttpProcessingError) as e:
                    logger.warning(f"[Attempt {attempt}/10] Failed to download {url}: {e}")
                    if attempt == 10:
                        logger.error(f"{url} download failed after 10 attempts")
                        return False
                    await asyncio.sleep(0.25 * attempt)
                    
                except asyncio.CancelledError:
                    logger.warning(f"Download cancelled for {Color.fg('light_gray')}{url}{Color.reset()}")
                    path = Path(file_path)
                    try:
                        if path.exists():
                            path.unlink()
                            logger.info(f"Removed partial file: {file_path}")
                    except OSError as e:
                        logger.warning(f"Failed to remove file {file_path}: {e}")
                    raise
            return False

        # Use provided session or create temporary one
        if session:
            return await _download_with_session(session)
        else:
            connector = aiohttp.TCPConnector(limit=ImageDownloader._connector_limit)
            async with aiohttp.ClientSession(
                headers=ImageDownloader._headers,
                timeout=ImageDownloader._timeout,
                connector=connector
            ) as temp_session:
                return await _download_with_session(temp_session)

    @classmethod
    def shutdown_executor(cls) -> None:
        """Shutdown the thread pool executor gracefully."""
        cls._file_io_executor.shutdown(wait=True)
        logger.info(f"{Color.fg('light_gray')}File I/O executor shutdown complete{Color.reset()}")
