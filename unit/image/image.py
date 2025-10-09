import asyncio
import random
import os
import string
import shutil

import httpx

from typing import Any, Dict, List, Tuple, Optional

from static.color import Color
from lib.__init__ import dl_folder_name, use_proxy, FilenameSanitizer, OutputFormatter
from lib.save_json_data import save_json_data
from lib.load_yaml_config import CFG
from lib.path import Path
from unit.data.data import get_formatted_publish_date, get_timestamp_formact
from unit.handle.handle_log import setup_logging
from unit.http.request_berriz_api import Playback_info, Public_context
from unit.image.class_ImageDownloader import ImageDownloader
#from unit.image.class_ImageDownloaderQUIC import ImageDownloader
from unit.image.parse_playback_contexts import IMG_PlaybackContext
from unit.image.parse_public_contexts import IMG_PublicContext


logger = setup_logging('image', 'mint')

    
ContextList = List[Dict[str, Any]]


class IMGmediaDownloader:
    
    semaphore: asyncio.Semaphore = asyncio.Semaphore(7)
    
    def __init__(self) -> None:
        self.Playback_info = Playback_info()
        self.Public_context = Public_context()

    def printer_image_info(self, public_ctx: IMG_PublicContext):
        logger.info(
            f"{Color.fg('magenta')}{public_ctx.title} "
            f"{Color.fg('cyan')}{public_ctx.community_name} "
            f"{Color.fg('gray')}{public_ctx.media_id}{Color.reset()}"
        )
        
    async def process_single_media(self,
                                   public_ctx: IMG_PublicContext,
                                   playback_ctx: IMG_PlaybackContext) -> None:
        async with IMGmediaDownloader.semaphore:
            folder_mgr: FolderManager = FolderManager(public_ctx)
            parser: ImageUrlParser = ImageUrlParser(playback_ctx)
            title: str = FilenameSanitizer.sanitize_filename(public_ctx.title)
            folder: Path = await folder_mgr.create_image_folder()
            json_path: Path = folder / f"{folder.name}{title}.json"
            await save_json_data(json_path)._write_file(json_path, public_ctx.to_json())
            self.printer_image_info(public_ctx)
            await parser.parse_and_download(folder)

    async def get_content(self, media_id: str) -> Tuple[IMG_PublicContext, IMG_PlaybackContext]:
        pub, play = await asyncio.gather(
            self.Public_context.get_public_context(media_id, use_proxy),
            self.Playback_info.get_playback_context(media_id, use_proxy),
            return_exceptions=True
        )
        if isinstance(pub, Exception) or isinstance(play, Exception):
            raise RuntimeError(f"fetch failed for {media_id}")
        return IMG_PublicContext(pub), IMG_PlaybackContext(play)

    async def fetch_and_process(self, media_id: str) -> None:
        public_ctx, playback_ctx = await self.get_content(media_id)
        await self.process_single_media(public_ctx, playback_ctx)

    async def run_image_dl(self, media_ids: List[str]) -> None:
        # 直接為整張清單建立並行任務
        tasks = [
            asyncio.create_task(self.fetch_and_process(mid))
            for mid in media_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 記錄例外
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.warning(f"media_id={media_ids[idx]} failed: {res}")


class ImageUrlParser:
    def __init__(self, _IMG_PlaybackContext: IMG_PlaybackContext) -> None:
        self.IMG_PlaybackContext: IMG_PlaybackContext = _IMG_PlaybackContext
        self.ImageDownloader: ImageDownloader = ImageDownloader()

    async def parse_and_download(self, folder_path: Path) -> None:
        try:
            tasks: List[asyncio.Task[Any]] = []

            for idx, image in enumerate(self.IMG_PlaybackContext.images):
                url: Optional[str] = image.get("imageUrl")
                if not url:
                    continue
                name: str = Path(url).name or f"image_{idx}.png"
                # 移除所有query参数
                name = name.split("?")[0]
                IMG_File_Path: Path = Path(folder_path) / name
                task: asyncio.Task[Any] = asyncio.create_task(self._download(url, IMG_File_Path))
                tasks.append(task)
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.warning(f"Download cancelled. Cleaning up folder...")
            if folder_path and os.path.isdir(folder_path):
                logger.info(f"{Color.fg('light_gray')}Removing folder: {folder_path}{Color.reset()}")
                shutil.rmtree(folder_path, ignore_errors=True)
                raise KeyboardInterrupt('Cancelled img download by user.')
        except Exception as e:
            if folder_path and os.path.isdir(folder_path):
                shutil.rmtree(folder_path, ignore_errors=True)
                logger.exception(f"Unexpected error during download: {e}")

    async def _download(self, url: httpx.URL, file_path: Path) -> None:
        await self.ImageDownloader.download_image(url, file_path)


class FolderManager():
    def __init__(self, _IMG_PublicContext: IMG_PublicContext) -> None:
        self.IMG_PublicContext: IMG_PublicContext = _IMG_PublicContext
        self.title: str = FilenameSanitizer.sanitize_filename(self.IMG_PublicContext.title)
        self.community_name: str = self.IMG_PublicContext.community_name

    async def create_image_folder(self) -> Path:
        """Create a folder for images. If exists, append random 5-letter suffix."""
        fmt = CFG['Donwload_Dir_Name']['date_formact']
        fm:str = get_timestamp_formact(fmt) # %y%m%d_%H-%M
        dt:str = get_formatted_publish_date(self.IMG_PublicContext.published_at, fm)
        video_meta: Dict[str, str] = {
            "date": dt,
            "title": self.title,
            "community_name": self.community_name,
            "source": "Berriz",
            "tag": CFG['output_template']['tag']
        }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        return await self._ensure_unique_folder(folder_name)

    async def _ensure_unique_folder(self, folder_name: str) -> Path:
        base_dir = Path(dl_folder_name) / self.IMG_PublicContext.community_name / "Images"
        base_dir.mkdirp()
        while True:
            suffix = "".join(random.choices(string.ascii_lowercase, k=5))
            candidate = base_dir / (f"{folder_name}" if suffix == "" else f"{folder_name} [{suffix}]")
            try:
                candidate.mkdirp()
                return candidate
            except FileExistsError:
                continue