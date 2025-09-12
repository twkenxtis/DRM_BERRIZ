import asyncio
import random
import re
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiofiles
import httpx
from fake_useragent import UserAgent

from typing import Any, Dict, List, Tuple, Union

from mystate.fanclub import fanclub_main
from static.color import Color
from unit.community import custom_dict, get_community
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import Playback_info, Public_context
from unit.image.parse_playback_contexts import parse_playback_contexts
from unit.image.parse_public_contexts import parse_public_contexts


logger = setup_logging('image', 'mint')


class FanClubFilter:
    async def is_fanclub():
        context = await fanclub_main()
        """None - not fanclub"""
        return context
    
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
    def __init__(self):
        pass

    async def create_image_folder(self, title: str, publishedAt: str, community_id: int) -> str | None:
        """Create a folder for images. If exists, append random 5-letter suffix."""
        time_str = await DateTimeFormatter.format_published_at(publishedAt)
        safe_title = await FilenameSanitizer.sanitize_filename(title)
        
        community_name = await self.get_community_name(community_id)
        if type(community_name) == str:
            community_name = custom_dict(community_name)
        if community_name is None:
            community_name = await self.get_community_name(community_id)
        
        base_dir: Path = Path.cwd() / "downloads" / community_name / "images"
        base_folder_name = f"{time_str} {community_name} - {safe_title}"
        folder_path = base_dir / base_folder_name

        try:
            await asyncio.to_thread(base_dir.mkdir, parents=True, exist_ok=True)
            while await asyncio.to_thread(folder_path.exists):
                random_suffix = "".join(random.choices(string.ascii_lowercase, k=5))
                folder_path = base_dir / f"{base_folder_name} [{random_suffix}]"
            await asyncio.to_thread(folder_path.mkdir)
            return str(folder_path.resolve())
        except Exception as e:
            if isinstance(e, OSError) and e.winerror == 183:
                logger.warning(f"Folder already exists, retrying with new suffix: {folder_path!r}")
                try:
                    # Retry with new suffix
                    while await asyncio.to_thread(folder_path.exists):
                        suffix = "".join(random.choices(string.ascii_lowercase, k=5))
                        folder_path = base_dir / f"{base_folder_name} [{suffix}]"
                    await asyncio.to_thread(folder_path.mkdir)
                    return str(folder_path.resolve())
                except Exception as retry_error:
                    logger.error(f"Retry failed: {folder_path!r}, reason: {retry_error}")
                    return None
            else:
                logger.error(f"Failed to create folder: {folder_path!r}, reason: {e}")
                return 
        
    async def get_community_name(self, community_id:int):
        n = await get_community(community_id)
        return n


class ImageDownloader:
    """Handles downloading images from URLs."""
    def get_header():
        return {
        "User-Agent": UserAgent().chrome,
        "Cache-Control": "no-cache",
        "Accept-Encoding": "identity",
        "Accept": "image/webp,image/png,image/jpeg,*/*",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "image",
        'Connection': 'keep-alive'
    }

    _headers = get_header()
    _timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0)
    _limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        
    @staticmethod
    async def _write_to_file(resp: httpx.Response, file_path: Union[str, Path]) -> None:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        write_queue = asyncio.Queue()
        async def writer_task():
            async with aiofiles.open(file_path, "wb") as f:
                while True:
                    data = await write_queue.get()
                    if data is None:
                        break
                    await f.write(data)
                    write_queue.task_done()
        writer = asyncio.create_task(writer_task())
        try:
            async for chunk in resp.aiter_bytes(25565):
                await write_queue.put(chunk)
            await write_queue.join()
            
        finally:
            await write_queue.put(None)
            await writer

    @staticmethod
    async def download_image(url: str, file_path: Union[str, Path]) -> None:
        for attempt in range(1, 11):
            try:
                async with httpx.AsyncClient(
                    headers=ImageDownloader._headers,
                    timeout=ImageDownloader._timeout,
                    limits=ImageDownloader._limits,
                    http2=True,
                ) as client:
                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()

                        write_task = asyncio.create_task(
                            ImageDownloader._write_to_file(resp, file_path)
                        )
                        await write_task

                logger.info(f"{Color.fg('periwinkle')}{file_path}{Color.reset()}")
                return

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"[Attempt {attempt}/10] Failed to download {url}: {e}")
                if attempt == 10:
                    logger.error(f"{url} download failed after 10 attempts")
                    raise

            except asyncio.CancelledError:
                logger.warning(f"File write cancelled for {Color.fg('light_gray')}{url}{Color.reset()}")
                try:
                    if await aiofiles.os.path.exists(file_path):
                        await aiofiles.os.remove(file_path)
                        logger.info(f"Removed partial file: {file_path}")
                except OSError as e:
                    logger.warning(f"Failed to remove file {file_path}: {e}")
                raise

    @staticmethod
    async def download_images_batch(
        tasks: List[Tuple[str, Union[str, Path]]], max_concurrency: int = 25
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

    async def parse_and_download(
        self, images: List[Dict[str, Any]], folder: str
    ) -> None:
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


async def run_image_dl(media_ids: list, max_concurrent: int = 23):
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(
        headers=ImageDownloader._headers,
        timeout=ImageDownloader._timeout,
        limits=ImageDownloader._limits,
        http2=True,
    ) as client:
        downloader = ImageDownloader()
        downloader._client = client

        image_parser = ImageUrlParser(downloader)
        folder_manager = FolderManager()

        async def process_single_media(media_id: str):
            async with semaphore:
                try:
                    public_ctxs, playback_ctxs = await asyncio.gather(
                        Public_context().get_public_context(media_id),
                        Playback_info().get_playback_context(media_id),
                        return_exceptions=True,
                    )

                    if isinstance(public_ctxs, Exception) or isinstance(
                        playback_ctxs, Exception
                    ):
                        logger.error(f"Failed to fetch contexts for {media_id}")
                        return

                    _, title, publishedAt, community_id = await parse_public_contexts(public_ctxs)
                    images = await parse_playback_contexts(playback_ctxs)

                    folder = await folder_manager.create_image_folder(
                        title, publishedAt, community_id
                    )
                    await image_parser.parse_and_download(images, folder)

                except Exception as e:
                    logger.error(f"Failed to process media {media_id}: {e}")

        chunks = [media_ids[i : i + 25] for i in range(0, len(media_ids), 25)]

        for chunk in chunks:
            tasks = [process_single_media(media_id) for media_id in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)
