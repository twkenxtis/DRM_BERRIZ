import asyncio
import random
import re
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typing import Any, Dict, List

from mystate.fanclub import fanclub_main
from unit.community import custom_dict, get_community
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import Playback_info, Public_context
from unit.image.class_ImageDownloader import ImageDownloader
from unit.image.parse_playback_contexts import parse_playback_contexts
from unit.image.parse_public_contexts import parse_public_contexts


logger = setup_logging('image', 'mint')

    
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

    def __init__(self, *, logger=None):
        self.logger = logger

    # Chunk 1: 入口
    async def create_image_folder(self, title: str, publishedAt: str, community_id: int) -> str | None:
        """Create a folder for images. If exists, append random 5-letter suffix."""
        time_str, safe_title = await self._format_time_and_title(publishedAt, title)
        community_name = await self._resolve_community_name(community_id)

        base_dir, base_folder_name, folder_path = self._compute_base_paths(
            time_str, safe_title, community_name
        )

        try:
            # 嘗試創建唯一資料夾（若存在則在內部選新名稱）
            folder_path = await self._ensure_unique_folder(base_dir, base_folder_name, folder_path)
            # 回傳絕對路徑字串
            return str((await asyncio.to_thread(folder_path.resolve)))
        except OSError as e:
            # Windows 183: 已存在（可能是 exists 與 mkdir 之間的競態）
            if getattr(e, "winerror", None) == 183:  # ERROR_ALREADY_EXISTS
                if self.logger:
                    self.logger.warning(f"Folder exists, retrying with suffix: {folder_path!r}")
                try:
                    folder_path = await self._retry_unique_folder(base_dir, base_folder_name)
                    return str((await asyncio.to_thread(folder_path.resolve)))
                except Exception as retry_error:
                    if self.logger:
                        self.logger.error(f"Retry failed: {folder_path!r}, reason: {retry_error}")
                    return None
            # 其他系統錯誤
            if self.logger:
                self.logger.error(f"Failed to create folder: {folder_path!r}, reason: {e}")
            return None

    # Chunk 2: 時間字串與標題清理
    async def _format_time_and_title(self, published_at: str, title: str) -> tuple[str, str]:
        time_str = await DateTimeFormatter.format_published_at(published_at)
        safe_title = await FilenameSanitizer.sanitize_filename(title)
        return time_str, safe_title

    # Chunk 3: 社羣名稱解析（規範化成字串）
    async def _resolve_community_name(self, community_id: int) -> str:
        community_name = await self.get_community_name(community_id)
        if isinstance(community_name, str):
            mapped = custom_dict(community_name)
            community_name = mapped
        if community_name is None:
            # 簡單重試一次（資料來源暫時失敗時）
            community_name = await self.get_community_name(community_id)
        return str(community_name)

    async def get_community_name(self, community_id: int):
        # 外部 async API 呼叫
        n = await get_community(community_id)
        return n

    # Chunk 4: 路徑計算（跨平臺）
    def _compute_base_paths(self, time_str: str, safe_title: str, community_name: str):
        base_dir: Path = Path.cwd() / "downloads" / community_name / "images"
        base_folder_name = f"{time_str} {community_name} - {safe_title}"
        folder_path = base_dir / base_folder_name
        return base_dir, base_folder_name, folder_path

    # Chunk 5: 唯一資料夾建立與重試
    async def _ensure_unique_folder(self, base_dir: Path, base_folder_name: str, folder_path: Path) -> Path:
        # 先建立父目錄（冪等）：parents=True, exist_ok=True，避免父層競態
        await asyncio.to_thread(base_dir.mkdir, parents=True, exist_ok=True)

        # 嘗試先挑一個可用名稱
        while await asyncio.to_thread(folder_path.exists):
            random_suffix = "".join(random.choices(string.ascii_lowercase, k=5))
            folder_path = base_dir / f"{base_folder_name}  [{random_suffix}]"

        # 建立資料夾；若 exists 與 mkdir 間被搶先，Windows 可能丟 183 [web:9]
        await asyncio.to_thread(folder_path.mkdir)
        return folder_path

    async def _retry_unique_folder(self, base_dir: Path, base_folder_name: str) -> Path:
        # 一直嘗試，直到成功建立
        while True:
            suffix = "".join(random.choices(string.ascii_lowercase, k=5))
            candidate = base_dir / f"{base_folder_name}  [{suffix}]"
            try:
                if not await asyncio.to_thread(candidate.exists):
                    await asyncio.to_thread(candidate.mkdir)
                    return candidate
            except OSError as e:
                # 被搶先建立則重試新的後綴
                if getattr(e, "winerror", None) == 183:
                    continue
                raise


class ImageUrlParser:
    """Parses image URLs and manages their download."""

    def __init__(self, max_concurrent: int = 23):
        self.downloader = ImageDownloader()
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


class IMGmediaDownloader:
    def __init__(self, max_concurrent: int = 23):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.folder_manager = FolderManager()

    async def process_single_media(self, media_id: str):
        async with self.semaphore:
            try:
                async with asyncio.TaskGroup() as tg:
                    context_task = tg.create_task(self.get_all_context(media_id))
                public_ctxs, playback_ctxs = await context_task

                async with asyncio.TaskGroup() as tg:
                    images_task = tg.create_task(parse_playback_contexts(playback_ctxs))
                    public_info_task = tg.create_task(parse_public_contexts(public_ctxs))

                images, public_info = await asyncio.gather(images_task, public_info_task)
                _, title, publishedAt, community_id = public_info

                folder = await self.folder_manager.create_image_folder(title, publishedAt, community_id)
                await ImageUrlParser().parse_and_download(images, folder)

            except* Exception as eg:
                for exc in eg.exceptions:
                    logger.error(f"Task group error in media {media_id}: {exc}")

    async def run_image_dl(self, media_ids: list[str]):
        chunks = [media_ids[i : i + 13] for i in range(0, len(media_ids), 13)]
        for chunk in chunks:
            tasks = [self.process_single_media(mid) for mid in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def get_all_context(self, media_id: str):
        public_ctxs, playback_ctxs = await asyncio.gather(
            self.get_public_context(media_id),
            self.get_playback_context(media_id),
            return_exceptions=True,
        )
        if isinstance(public_ctxs, Exception) or isinstance(playback_ctxs, Exception):
            logger.error(f"Failed to fetch contexts for {media_id}")
            return None, None
        return public_ctxs, playback_ctxs

    def get_public_context(self, media_id: str):
        return Public_context().get_public_context(media_id)

    def get_playback_context(self, media_id: str):
        return Playback_info().get_playback_context(media_id)
    
