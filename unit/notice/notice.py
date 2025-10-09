import asyncio
import random
import string
import shutil
from typing import Any, Dict, List, Optional

import orjson

from lib.__init__ import dl_folder_name, FilenameSanitizer
from lib.path import Path
from lib.save_json_data import save_json_data
from static.color import Color
from static.parameter import paramstore
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
        community = FilenameSanitizer.sanitize_filename(raw_name)
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

    async def get_community_name(self, community_id: int) -> Optional[str]:
        custom_cm_name = await custom_dict(await get_community(community_id))
        return custom_cm_name


class MainProcessor:
    
    completed = 0
    
    """Parses data & image URLs and manages their download."""
    def __init__(self, notice_media: Dict, folder: str, total :int):
        self.notice_media = notice_media
        self.fetcher: NoticeINFOFetcher = self.notice_media['fetcher']
        self.folder_path: Path = Path(folder)
        self.FDTF = File_date_time_formact(notice_media['folderName'], notice_media['video_meta'])
        self.new_file_name = self.FDTF.new_file_name()
        self.body: str = self.fetcher.get_body()
        self.DownloadImage = DownloadImage(self.body, self.folder_path)
        self.title: str = FilenameSanitizer.sanitize_filename(self.fetcher.get_title())
        self.total = total
        self.save_json_data = save_json_data(self.folder_path)

    async def parse_and_download(self) -> None:
        """Parse data image URLs and download them with concurrency control."""
        tasks = (
            asyncio.create_task(self.process_html()),
            asyncio.create_task(self.process_image()),
            asyncio.create_task(self.save_notice_json()),
        )
        await asyncio.gather(*tasks)
    
    async def process_html(self) -> None:
        MainProcessor.completed += 1
        logger.info(
            f"{Color.fg('gray')}Notice: [{Color.fg('mint')}{MainProcessor.completed}"
            f"{Color.fg('gray')}/{Color.fg('mint')}{self.total}{Color.fg('gray')}]"
            f"({Color.fg('fern')}{MainProcessor.completed/self.total*100:.1f}{Color.fg('gray')}%)"
        )
        ISO8601: str = self.fetcher.get_reservedAt()
        await SaveHTML(self.title, ISO8601, self.body, self.folder_path, self.new_file_name).update_template_file()
        
    async def save_notice_json(self):
        """Save notice data to json file."""
        data = dict(self.notice_media)  # 複製一份，避免動到原始資料
        data.pop("fetcher", None)

        json_data = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        json_file_path = Path(self.folder_path) / f"{self.title}.json"
        await self.save_json_data._write_file(json_file_path, json_data)
        
    async def process_image(self) -> None:
        if paramstore.get('nodl') is True:
            logger.info(f"{Color.fg('light_gray')}Skip downloading{Color.reset()} {Color.fg('light_gray')}NOTICE")
        else:
            await self.DownloadImage.download_images()


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
                    folder: str = await self.folder(notice_media)
                    await MainProcessor(notice_media, folder, len(self.selected_media)).parse_and_download()
                    return "OK"
                except asyncio.CancelledError:
                    await self.handle_cancel()
                    raise asyncio.CancelledError
        tasks = [asyncio.create_task(process(index)) for index in self.selected_media]
        await asyncio.gather(*tasks)

    async def notice_media(self, index: Dict[str, Any]) -> Dict[str, Any]:
        data = await self.get_notice_info(index, index["mediaId"], index["communityId"])
        logger.debug(data)
        return data
        
    async def folder(self, notice_media: Dict[str, Any]) -> str:
        folder = await self.folder_manager.create_folder(
            notice_media["folderName"],
            notice_media["communityId"],
        )
        self.folder_path: Path = Path(folder)
        return self.folder_path
        
    async def get_notice_info(self, media: Dict[str, Any], communityNoticeId: int, communityId: int) -> Dict[str, Any]:
        try:
            get_notice_info_task = BoardNoticeINFO(media).request_notice_info(communityNoticeId, communityId)
            return await get_notice_info_task
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