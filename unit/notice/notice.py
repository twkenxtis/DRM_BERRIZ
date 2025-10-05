import asyncio
import difflib
import random
import string
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.__init__ import dl_folder_name
from static.color import Color
from unit.post.post import File_date_time_formact
from unit.handle.handle_board_from import BoardNoticeINFO, NoticeINFOFetcher
from unit.community.community import custom_dict, get_community
from unit.handle.handle_log import setup_logging
from unit.notice.save_html import SaveHTML
from unit.notice.get_body_images import DownloadImage


logger = setup_logging('notice', 'forest_green')


class FolderManager:
    """管理下載的資料夾創建"""
    def __init__(self):
        self._lock = asyncio.Lock()

    async def create_folder(self, folder_name: str, community_id: int) -> Optional[str]:
        raw_name = await self.get_community_name(community_id)
        community = await self._sanitize_name(raw_name)
        base_dir = Path.cwd() / dl_folder_name / community / 'NOTICE'
        try:
            async with self._lock:
                path = await asyncio.to_thread(
                    self._make_unique_dir, base_dir, folder_name
                    )
            return str(path.resolve())
        except Exception as e:
            logger.error(f"create_folder failed: {e!r}")
            return None

    def _make_unique_dir(self, base_dir: Path, name: str) -> Path:
        """同步、原子地建立 base_dir/name，若已存在則加隨機後綴重試"""
        base_dir.mkdir(parents=True, exist_ok=True)
        candidate = base_dir / name

        while True:
            try:
                candidate.mkdir(exist_ok=False)
                return candidate
            except FileExistsError:
                suffix = "".join(random.choices(string.ascii_lowercase, k=5))
                candidate = base_dir / f"{name}  [{suffix}]"

    @staticmethod
    async def _sanitize_name(raw: Optional[str]) -> str:
        """將 None、空字串或特殊字元過濾成合法資料夾名，並套用 custom_dict 映射"""
        if not raw:
            return "unknown_community"

        mapped = await custom_dict(raw)
        if mapped is not None:
            raw = mapped

        # 過濾非法字元
        cleaned = "".join(c for c in raw if c.isalnum() or c in "-_ ")
        return cleaned.strip()

    async def get_community_name(self, community_id: int) -> Optional[str]:
        n = await get_community(community_id)
        return n


class MainProcessor:
    """Parses data & image URLs and manages their download."""
    def __init__(self, notice_media: Dict, folder: str):
        self.notice_media = notice_media
        self.fetcher: NoticeINFOFetcher = self.notice_media['fetcher']
        self.folder_path: Path = Path(folder)
        self.FDTF = File_date_time_formact(notice_media['folderName'], notice_media['video_meta'])
        self.new_file_name = self.FDTF.new_file_name()

    async def parse_and_download(self) -> None:
        """Parse data image URLs and download them with concurrency control."""
        tasks = (
            asyncio.create_task(self.process_html()),
            asyncio.create_task(self.process_image())
        )
        await asyncio.gather(*tasks)
    
    async def process_html(self) -> None:
        logger.info("Generating HTML...")
        title: str = self.fetcher.get_title()
        ISO8601: str = self.fetcher.get_reservedAt()
        body: str = self.fetcher.get_body()
        await SaveHTML(title, ISO8601, body, self.folder_path, self.new_file_name).update_template_file()

    async def process_image(self) -> None:
        body: str = self.fetcher.get_body()
        await DownloadImage(body, self.folder_path).request_image()


class RunNotice:
    def __init__(self, selected_media: List[Dict]):
        self.selected_media: List[Dict[str, Any]] = selected_media
        self.folder_manager: FolderManager = FolderManager()
        self.folder_path = None
        self.folder_name = set()

    async def run_notice_dl(self):
        """Top Async ENTER"""
        semaphore = asyncio.Semaphore(7)
        async def process(index: Dict[str, Any]) -> str:
            async with semaphore:
                try:
                    self.folder_name.add((index['title']))
                    notice_media: dict = await self.notice_media(index)
                    folder: str = await self.folder(await self.notice_media(index))
                    await MainProcessor(notice_media, folder).parse_and_download()
                    return "ok"
                except asyncio.CancelledError:
                    await self.handle_cancel()
                    raise asyncio.CancelledError
        tasks = [asyncio.create_task(process(index)) for index in self.selected_media]
        await asyncio.gather(*tasks)

    async def notice_media(self, index: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.get_notice_info(index, index["mediaId"], index["communityId"])
        return data[0]
        
    async def folder(self, notice_media: Dict[str, Any]) -> str:
        folder = await self.folder_manager.create_folder(
            notice_media["folderName"],
            notice_media["communityId"],
        )
        self.folder_path: Path = Path(folder)
        return self.folder_path
        
    async def get_notice_info(self, media: Dict[str, Any], communityNoticeId: int, communityId: int) -> Dict[str, Any]:
        try:
            get_notice_info_task = [asyncio.create_task(BoardNoticeINFO(media).request_notice_info(communityNoticeId, communityId))]
            return await asyncio.gather(*get_notice_info_task)
        except asyncio.CancelledError:
            await self.handle_cancel()
            raise asyncio.CancelledError
        
    async def handle_cancel(self):
        if self.folder_path.parent.iterdir():
            for all_folder in self.folder_path.parent.iterdir():
                path = self.folder_path.parent / all_folder
                E = not any(path.iterdir())
                if E and path.name.strip() in  all_folder.name.strip():
                    logger.warning(f"async_dl_cancel: delete folder {Color.fg('light_gray')}{path}{Color.reset()}")
                    shutil.rmtree(path)