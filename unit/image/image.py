import asyncio
import random
import re
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typing import Any, Dict, List, Union, Tuple, Optional

from static.color import Color
from static.api_error_handle import api_error_handle
from lib.__init__ import dl_folder_name
from unit.community import custom_dict, get_community
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import Playback_info, Public_context
from unit.image.class_ImageDownloader import ImageDownloader
from unit.image.parse_playback_contexts import parse_playback_contexts
from unit.image.parse_public_contexts import parse_public_contexts


logger = setup_logging('image', 'mint')

    
# 定義 API 回傳的上下文類型
ContextList = List[Dict[str, Any]]
PublicInfoTuple = Tuple[Any, str, str, int] # (media, title, publishedAt, community_id)


class FilenameSanitizer:
    """Handles sanitization of filenames to remove invalid characters."""

    @staticmethod
    # 函式是 async 的，所以需要註釋為 async def
    async def sanitize_filename(name: str) -> str:
        """Remove invalid characters from a filename and strip whitespace."""
        cleaned: str = re.sub(r'[\\/:\*\?"<>|]', "", name)
        return cleaned.strip()


class DateTimeFormatter:
    """Formats datetime strings for folder naming."""

    @staticmethod
    async def format_published_at(publishedAt: str) -> str:
        """Convert UTC publishedAt time to KST and format as string with 4-digit seconds."""
        # datetime.strptime 返回 datetime
        utc_time: datetime = datetime.strptime(publishedAt, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        kst_offset: timedelta = timedelta(hours=9)  # KST is UTC+9
        kst_time: datetime = utc_time + kst_offset
        return kst_time.strftime("%y%m%d %H-%M")


class FolderManager:
    """Manages folder creation for image downloads."""

    # logger 型別提示為 Any，因為我們知道它是一個 logger 物件
    def __init__(self, *, logger: Optional[Any] = None) -> None:
        self.logger: Optional[Any] = logger

    # Chunk 1: 入口
    # 回傳值為 str (絕對路徑) 或 None
    async def create_image_folder(self, title: str, publishedAt: str, community_id: int) -> Optional[str]:
        """Create a folder for images. If exists, append random 5-letter suffix."""
        time_str: str
        safe_title: str
        time_str, safe_title = await self._format_time_and_title(publishedAt, title)
        community_name: str = await self._resolve_community_name(community_id)

        base_dir: Path
        base_folder_name: str
        folder_path: Path
        base_dir, base_folder_name, folder_path = self._compute_base_paths(
            time_str, safe_title, community_name
        )

        try:
            # 嘗試創建唯一資料夾（若存在則在內部選新名稱）
            folder_path = await self._ensure_unique_folder(base_dir, base_folder_name, folder_path)
            # 使用 resolve() 取得絕對路徑，並轉為字串
            # asyncio.to_thread 返回 Path.resolve 的結果 (Path)
            resolved_path: Path = await asyncio.to_thread(folder_path.resolve)
            return str(resolved_path)
        except OSError as e:
            if getattr(e, "winerror", None) == 183:  # ERROR_ALREADY_EXISTS (Windows)
                if self.logger:
                    self.logger.warning(f"Folder exists, retrying with suffix: {folder_path!r}")
                try:
                    folder_path = await self._retry_unique_folder(base_dir, base_folder_name)
                    resolved_path: Path = await asyncio.to_thread(folder_path.resolve)
                    return str(resolved_path)
                except Exception as retry_error:
                    if self.logger:
                        self.logger.error(f"Retry failed: {folder_path!r}, reason: {retry_error}")
                    return None
            # 其他系統錯誤
            if self.logger:
                self.logger.error(f"Failed to create folder: {folder_path!r}, reason: {e}")
            return None

    # Chunk 2: 時間字串與標題清理
    async def _format_time_and_title(self, published_at: str, title: str) -> Tuple[str, str]:
        time_str: str = await DateTimeFormatter.format_published_at(published_at)
        safe_title: str = await FilenameSanitizer.sanitize_filename(title)
        return time_str, safe_title

    # Chunk 3: 社羣名稱解析（規範化成字串）
    async def _resolve_community_name(self, community_id: int) -> str:
        # get_community_name 返回 Union[str, int, None]
        community_name: Union[str, int, None] = await self.get_community_name(community_id)
        
        if isinstance(community_name, str):
            # custom_dict 返回 Optional[str]
            mapped: Optional[str] = await custom_dict(community_name)
            if mapped is not None:
                community_name = mapped
        
        if community_name is None:
            # 簡單重試一次
            community_name = await self.get_community_name(community_id)
            
            # 如果重試仍失敗，則使用預設值
            if community_name is None or isinstance(community_name, int):
                community_name = str(community_id)
                
        return str(community_name)

    # get_community 返回 Union[str, int, None]
    async def get_community_name(self, community_id: int) -> Union[str, int, None]:
        # 外部 async API 呼叫
        n: Union[str, int, None] = await get_community(community_id)
        return n

    # Chunk 4: 路徑計算（跨平臺）
    def _compute_base_paths(self, time_str: str, safe_title: str, community_name: str) -> Tuple[Path, str, Path]:
        # Path 物件
        base_dir: Path = Path.cwd() / dl_folder_name / community_name / "images"
        base_folder_name: str = f"{time_str} {community_name} - {safe_title}"
        folder_path: Path = base_dir / base_folder_name
        return base_dir, base_folder_name, folder_path

    # Chunk 5: 唯一資料夾建立與重試
    async def _ensure_unique_folder(self, base_dir: Path, base_folder_name: str, folder_path: Path) -> Path:
        # 先建立父目錄（冪等）
        await asyncio.to_thread(base_dir.mkdir, parents=True, exist_ok=True)

        # 嘗試先挑一個可用名稱
        # asyncio.to_thread(folder_path.exists) 返回 bool
        while await asyncio.to_thread(folder_path.exists):
            random_suffix: str = "".join(random.choices(string.ascii_lowercase, k=5))
            folder_path = base_dir / f"{base_folder_name}  [{random_suffix}]"

        # 建立資料夾
        await asyncio.to_thread(folder_path.mkdir)
        return folder_path

    async def _retry_unique_folder(self, base_dir: Path, base_folder_name: str) -> Path:
        # 一直嘗試，直到成功建立
        while True:
            suffix: str = "".join(random.choices(string.ascii_lowercase, k=5))
            candidate: Path = base_dir / f"{base_folder_name}  [{suffix}]"
            try:
                # asyncio.to_thread(candidate.exists) 返回 bool
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

    downloader: ImageDownloader
    semaphore: asyncio.Semaphore

    def __init__(self, max_concurrent: int = 23) -> None:
        self.downloader: ImageDownloader = ImageDownloader() # 假設 ImageDownloader 有一個無參數的 __init__
        self.semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)

    async def parse_and_download(
        self, images: List[Dict[str, Any]], folder: str
    ) -> None:
        """Parse image URLs and download them with concurrency control."""
        folder_path: Path = Path(folder)
        tasks: List[asyncio.Task[Any]] = []

        for idx, image in enumerate(images):
            # image.get("imageUrl") 返回 Optional[str]
            url: Optional[str] = image.get("imageUrl")
            if not url:
                continue
            
            # Path(url).name 返回 Optional[str]
            name: str = Path(url).name or f"image_{idx}.jpg"
            # 對 name 進行分段處理
            name = name.split("?")[0]
            file_path: Path = folder_path / name

            # asyncio.create_task 返回 asyncio.Task
            task: asyncio.Task[Any] = asyncio.create_task(self._download_with_semaphore(url, file_path))
            tasks.append(task)

        await asyncio.gather(*tasks)

    # _download_with_semaphore 是一個內部方法，不需要回傳值 (None)
    async def _download_with_semaphore(self, url: str, file_path: Path) -> None:
        async with self.semaphore:
            await self.downloader.download_image(url, file_path)


class IMGmediaDownloader:
    semaphore: asyncio.Semaphore
    folder_manager: FolderManager

    def __init__(self, max_concurrent: int = 23) -> None:
        self.semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self.folder_manager: FolderManager = FolderManager(logger=logger)

    # process_single_media 是一個協程，沒有明確的回傳值 (None)
    async def process_single_media(self, media_id: str) -> None:
        async with self.semaphore:
            try:
                # 使用 TaskGroup 來結構化並行任務
                async with asyncio.TaskGroup() as tg:
                    # TaskGroup.create_task 返回 asyncio.Task[Tuple[ContextList, ContextList]]
                    context_task: asyncio.Task[Tuple[ContextList, ContextList]] = tg.create_task(self.get_all_context(media_id))
                
                # context_task 的結果
                public_ctxs: ContextList
                playback_ctxs: ContextList
                public_ctxs, playback_ctxs = await context_task
                
                # 檢查是否為 None (表示 get_all_context 中有失敗)
                if public_ctxs is None or playback_ctxs is None:
                    return

                async with asyncio.TaskGroup() as tg:
                    # parse_playback_contexts 返回 List[Dict[str, Any]]
                    images_task: asyncio.Task[List[Dict[str, Any]]] = tg.create_task(parse_playback_contexts(playback_ctxs))
                    # parse_public_contexts 返回 PublicInfoTuple
                    public_info_task: asyncio.Task[PublicInfoTuple] = tg.create_task(parse_public_contexts(public_ctxs))

                images: List[Dict[str, Any]]
                public_info: PublicInfoTuple
                # asyncio.gather 返回 Tuple[List[Dict[str, Any]], PublicInfoTuple]
                images, public_info = await asyncio.gather(images_task, public_info_task)
                
                # public_info 包含 (media, title, publishedAt, community_id)
                _, title, publishedAt, community_id = public_info

                # create_image_folder 返回 Optional[str]
                folder: Optional[str] = await self.folder_manager.create_image_folder(title, publishedAt, community_id)
                if folder is None:
                    logger.error(f"Failed to create folder for media {media_id}. Skipping download.")
                    return
                
                # 實例化並執行下載
                await ImageUrlParser().parse_and_download(images, folder)

            # 使用 ExceptionGroup (try* ... except*) 來處理 TaskGroup 異常
            except* Exception as eg:
                for exc in eg.exceptions:
                    logger.error(f"Task group error in media {media_id}: {exc}")

    # run_image_dl 是一個協程，沒有明確的回傳值 (None)
    async def run_image_dl(self, media_ids: List[str]) -> None:
        # chunks 是一個 List[List[str]]
        chunks: List[List[str]] = [media_ids[i : i + 13] for i in range(0, len(media_ids), 13)]
        for chunk in chunks:
            # tasks 是 List[asyncio.Task[None]]
            tasks: List[asyncio.Task[None]] = [self.process_single_media(mid) for mid in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)

    # get_all_context 返回 Tuple[Optional[ContextList], Optional[ContextList]]
    async def get_all_context(self, media_id: str) -> Tuple[Optional[ContextList], Optional[ContextList]]:
        # asyncio.gather 返回 Tuple[Union[ContextList, Exception], Union[ContextList, Exception]]
        results: Tuple[Union[ContextList, Exception], Union[ContextList, Exception]] = await asyncio.gather(
            self.get_public_context(media_id),
            self.get_playback_context(media_id),
            return_exceptions=True,
        )
        public_ctxs: Union[ContextList, Exception] = results[0]
        playback_ctxs: Union[ContextList, Exception] = results[1]

        if isinstance(public_ctxs, Exception) or isinstance(playback_ctxs, Exception):
            logger.error(f"Failed to fetch contexts for {media_id}")
            return None, None
            
        # 假設 public_ctxs[0]['data']['media'] 返回 Dict[str, Any]
        media: Dict[str, Any] = public_ctxs[0]['data']['media']
        communityArtists: List[Dict[str, Any]] = public_ctxs[0]['data']['communityArtists']
        
        # 日誌輸出
        logger.info(
            f"{Color.fg('light_magenta')}{media['title']} "
            f"{Color.fg('light_cyan')}{communityArtists[0]['name']} "
            f"{Color.fg('light_gray')}{media['mediaId']}"
            f"{Color.reset()}"
        )
        
        # 檢查 API 錯誤碼
        if playback_ctxs[0]['code'] != '0000':
            # 假設 api_error_handle 返回 str
            error_message: str = api_error_handle(playback_ctxs[0]['code'])
            logger.warning(f"{Color.bg('maroon')}{error_message}{Color.reset()}")
            
        # 由於上面檢查了 Exception，這裡可以確定是 ContextList
        return public_ctxs, playback_ctxs

    # 假設 Public_context().get_public_context 返回 ContextList (實際是 Future/Awaitable，這裡假設它返回 ContextList)
    def get_public_context(self, media_id: str) -> Any:
        # 假設 Public_context() 返回一個包含 get_public_context 方法的物件
        return Public_context().get_public_context(media_id)

    def get_playback_context(self, media_id: str) -> Any:
        # 假設 Playback_info() 返回一個包含 get_playback_context 方法的物件
        return Playback_info().get_playback_context(media_id)