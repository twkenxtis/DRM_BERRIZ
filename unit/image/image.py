import asyncio
import logging
import os
import re
import random
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logging.handlers import TimedRotatingFileHandler

import aiofiles
import httpx

from typing import Any, Dict, List, Union, Tuple

from static.color import Color
from unit.http.request_berriz_api import Playback_info, Public_context
from unit.image.parse_public_contexts import parse_public_contexts
from unit.image.parse_playback_contexts import parse_playback_contexts


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
       f"{Color.fg('light_gray')}%(asctime)s [%(levelname)s] [%(name)s]: %(message)s {Color.reset()}"
    )

    logger = logging.getLogger(f"{Color.fg('mint')}image{Color.reset()}")
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
        filename="logs/image.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


logger = setup_logging()



class FilenameSanitizer:
    """Handles sanitization of filenames to remove invalid characters."""

    @staticmethod
    async def sanitize_filename(name: str) -> str:
        """Remove invalid characters from a filename and strip whitespace."""
        cleaned = re.sub(r'[\\/:\*\?"<>|]', "", name)
        return cleaned.strip()


class DateTimeFormatter:
    """Formats datetime strings for folder naming."""

    @staticmethod
    async def format_published_at(publishedAt: str) -> str:
        """Convert UTC publishedAt time to KST and format as string with 4-digit seconds."""
        utc_time = datetime.strptime(publishedAt, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        kst_offset = timedelta(hours=9)  # KST is UTC+9
        kst_time = utc_time + kst_offset
        return kst_time.strftime("%y%m%d %H-%M")


class FolderManager:
    """Manages folder creation for image downloads."""

    def __init__(self, base_dir: Path = Path.cwd() / "downloads" / "images"):
        self.base_dir = base_dir

    async def create_image_folder(self, title: str, publishedAt: str) -> str | None:
        """Create a folder for images. If exists, append random 5-letter suffix."""
        time_str = await DateTimeFormatter.format_published_at(publishedAt)
        safe_title = await FilenameSanitizer.sanitize_filename(title)
        base_folder_name = f"{time_str} IVE - {safe_title}"
        folder_path = self.base_dir / base_folder_name

        try:
            await asyncio.to_thread(self.base_dir.mkdir, parents=True, exist_ok=True)

            while await asyncio.to_thread(folder_path.exists):
                random_suffix = ''.join(random.choices(string.ascii_letters, k=5))
                folder_path = self.base_dir / f"{base_folder_name} [{random_suffix}]"

            await asyncio.to_thread(folder_path.mkdir)
            return str(folder_path.resolve())
        except Exception as e:
            logger.error(f"Failed to create folder: {folder_path!r}, reason: {e}")
            return None


class ImageDownloader:
    """Handles downloading images from URLs."""

    _headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"
    }
    _timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0)
    _limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)

    @staticmethod
    async def download_image(url: str, file_path: Union[str, Path]) -> None:
        try:
            async with httpx.AsyncClient(
                headers=ImageDownloader._headers,
                timeout=ImageDownloader._timeout,
                limits=ImageDownloader._limits,
                http2=True
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()

                    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(65536):
                            await f.write(chunk)
            logger.info(f"{Color.fg('light_gray')}{file_path}{Color.reset()}")
        except httpx.HTTPStatusError as e:
            logger.error(f"{url} download failed with code {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Failed to download {url}: {e}")
            raise

    @staticmethod
    async def download_images_batch(
        tasks: List[Tuple[str, Union[str, Path]]],
        max_concurrency: int = 10
    ) -> None:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def safe_download(url: str, path: Union[str, Path]):
            async with semaphore:
                try:
                    await ImageDownloader.download_image(url, path)
                except Exception as e:
                    logger.warning(f"Download failed for {url}: {e}")

        await asyncio.gather(*(safe_download(url, path) for url, path in tasks))


class ImageUrlParser:
    """Parses image URLs and manages their download."""

    def __init__(self, downloader: ImageDownloader, max_concurrent: int = 23):
        self.downloader = downloader
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def parse_and_download(self, images: List[Dict[str, Any]], folder: str) -> None:
        """Parse image URLs and download them with concurrency control."""
        folder_path = Path(folder)
        tasks = []
        
        for idx, image in enumerate(images):
            url = image.get("imageUrl")
            if not url:
                continue
            name = Path(url).name or f"image_{idx}.jpg"
            name = name.split("?")[0]
            file_path = folder_path / name
            
            task = asyncio.create_task(self._download_with_semaphore(url, file_path))
            tasks.append(task)
        
        await asyncio.gather(*tasks)

    async def _download_with_semaphore(self, url: str, file_path: Path):
        async with self.semaphore:
            await self.downloader.download_image(url, file_path)


class MediaDownloadOrchestrator:
    def __init__(self, max_media_tasks: int = 10):
        self.folder_manager = FolderManager()
        self.image_parser = ImageUrlParser(ImageDownloader())
        self._sem = asyncio.Semaphore(max_media_tasks)

    async def _fetch_contexts(self, media_id: str):
        pub_task = asyncio.create_task(Public_context().get_public_context(media_id))
        play_task = asyncio.create_task(Playback_info().get_playback_context(media_id))
        return await asyncio.gather(pub_task, play_task)

    async def run_download(self, media_id: str) -> None:
        async with self._sem:
            public_ctxs, playback_ctxs = await self._fetch_contexts(media_id)
            _, title, publishedAt = await parse_public_contexts(public_ctxs)
            images = await parse_playback_contexts(playback_ctxs)

            folder = await self.folder_manager.create_image_folder(title, publishedAt)
            await self.image_parser.parse_and_download(images, folder)

async def run_image_dl(media_ids: list, max_concurrent: int = 10):
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async with httpx.AsyncClient(
        headers=ImageDownloader._headers,
        timeout=ImageDownloader._timeout,
        limits=ImageDownloader._limits,
        http2=True
    ) as client:
        downloader = ImageDownloader()
        downloader._client = client
        
        image_parser = ImageUrlParser(downloader)
        folder_manager = FolderManager()
        
        async def process_single_media(media_id: str):
            async with semaphore:
                try:
                    # 並行獲取上下文
                    public_ctxs, playback_ctxs = await asyncio.gather(
                        Public_context().get_public_context(media_id),
                        Playback_info().get_playback_context(media_id),
                        return_exceptions=True
                    )
                    
                    if isinstance(public_ctxs, Exception) or isinstance(playback_ctxs, Exception):
                        logger.error(f"Failed to fetch contexts for {media_id}")
                        return
                    
                    _, title, publishedAt = await parse_public_contexts(public_ctxs)
                    images = await parse_playback_contexts(playback_ctxs)
                    
                    folder = await folder_manager.create_image_folder(title, publishedAt)
                    await image_parser.parse_and_download(images, folder)
                    
                except Exception as e:
                    logger.error(f"Failed to process media {media_id}: {e}")
        
        chunks = [media_ids[i:i + 100] for i in range(0, len(media_ids), 100)]
        
        for chunk in chunks:
            tasks = [process_single_media(media_id) for media_id in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.5)