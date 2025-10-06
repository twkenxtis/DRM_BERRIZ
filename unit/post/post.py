import asyncio
import os
import random
import shutil
import string
from datetime import datetime
from pathlib import Path

from typing import Any, Dict, List, Tuple, Optional

import aiofiles
import orjson
from httpx import URL
from lib.processbar import ProgressBar

from lib.__init__ import dl_folder_name, OutputFormatter
from lib.load_yaml_config import CFG
from lib.artis.request_artis import ArtisManger
from static.color import Color
from unit.post.save_html import SaveHTML
from unit.handle.handle_board_from import JsonBuilder, BoardFetcher
from unit.image.class_ImageDownloader import ImageDownloader
from unit.community.community import custom_dict
from unit.handle.handle_log import setup_logging


logger = setup_logging('post', 'maroon')


class FolderManager:
    """管理下載的資料夾創建"""
    def __init__(self, post_media: dict):
        self.post_media: dict = post_media
        self.folder_name: str = post_media['folderName']
        self.fetcher: BoardFetcher = post_media['fetcher']
        self.community_id: int = self.fetcher.get_board_community_id()
        self._lock = asyncio.Lock()

    async def create_folder(self) -> Optional[str]:
        community_name = self.post_media['communityName']
        custom_community_name = await custom_dict(community_name)
        base_dir = Path.cwd() / dl_folder_name / custom_community_name / self.fetcher.get_board_name()
        try:
            async with self._lock:
                path = await asyncio.to_thread(
                    self._make_unique_dir, base_dir
                    )
            return str(path.resolve())
        except Exception as e:
            logger.error(f"create_folder failed: {e!r}")
            return None

    def _make_unique_dir(self, base_dir: Path) -> Path:
        """同步、原子地建立 base_dir/name，若已存在則加隨機後綴重試"""
        base_dir.mkdir(parents=True, exist_ok=True)
        candidate = base_dir / self.folder_name

        while True:
            try:
                candidate.mkdir(exist_ok=False)
                return candidate
            except FileExistsError:
                suffix = "".join(random.choices(string.ascii_lowercase, k=5))
                candidate = base_dir / f"{self.folder_name}  [{suffix}]"


class MainProcessor:
    """Parses image URLs and manages their download."""
    def __init__(self, post_media: Dict, folder: str):
        self.post_media = post_media
        self.fetcher: BoardFetcher = post_media['fetcher']
        self.post_id = self.fetcher.get_postid()
        self.folder_path: Path = Path(folder)
        self.FDTF = File_date_time_formact(post_media['folderName'], post_media['video_meta'])
        self.new_file_name = self.FDTF.new_file_name()
        self.json_data_obj = PostJsonDate(self.post_media['index'], self.post_id, self.new_file_name)

    async def parse_and_download(self) -> None:
        """Parse image URLs and download them with concurrency control."""
        image_data, none_image_data = self.filter_post_data()
        try:
            if image_data:
                await self.process(image_data, True)
            elif none_image_data:
                await self.process(self.post_media, False)
        except Exception as e:
            logger.error(f"Error during parse_and_download: {e}")
                    
    async def process(self, data: List[Dict[str, Any]], TYPE: bool) -> None:
        image_list: List[URL] = []
        if not data or len(data) < 2:
            logger.warning("Invalid or insufficient data provided.")
            return
        try:
            if TYPE:
                raw_images = data[1]
                if not isinstance(raw_images, list):
                    logger.warning("data[1] is not a list.")
                    raw_images = []

                image_list = [img for img in raw_images if img]
                if not image_list:
                    logger.warning("No valid image URLs found in data[1]")

                try:
                    await self.download_images_concurrently(image_list, self.folder_path)
                except Exception as e:
                    logger.warning(f"Image download failed: {e}")

                first_name = Path(str(image_list[0])).name.split("?")[0] if image_list else "image-media"
                file_path = self.folder_path / f"{first_name}.json"
            else:
                file_path = self.folder_path / "non-image-media.json"
            await self.process_and_save(file_path, image_list, TYPE)
        except Exception as e:
            logger.exception(f"Error during media processing: {e}")
            
    async def process_and_save(self, file_path: Path, image_list: List[URL], TYPE: bool) -> None:
        await asyncio.gather(self.json_data_obj.save_json_file_to_folder(file_path, self.folder_path),
        make_html(self.post_media, self.folder_path, image_list, self.new_file_name).process_html(TYPE))


    def safe_filename_from_url(url: str, fallback: str = "image") -> str:
        name = Path(url).name or fallback
        return name.split("?")[0]

    async def download_images_concurrently(self, image_list: List[URL], folder_path: Path) -> None:
        for idx, image in enumerate(image_list):
            try:
                name = Path(str(image)).name or f"image_{idx}.jpg"
                name = name.split("?")[0]
                file_path = folder_path / name

                logger.debug(f"Downloading: {image} → \n{file_path}")
                await ImageDownloader.download_image(image, file_path)
            except Exception as e:
                logger.warning(f"Failed to download image {image}: {e}")


    def filter_post_data(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
            """過濾貼文資料，將包含圖片的資料與不包含圖片的資料分開
            
            Returns:
                Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: 
                    包含圖片的資料列表, 不包含圖片的資料列表
            """
            image_info = self.fetcher.get_photos()
            image_data, none_image_data = [], []
            
            for item in image_info:
                # 判斷條件：如果是列表或元組且包含任何內容（非空）
                if isinstance(item, (list, tuple)) and any(item):
                    # 符合條件：加入到圖片資料列表
                    image_data.append(item)
                else:
                    # 不符合條件：加入到無圖片資料列表
                    none_image_data.append(item)
            return image_data, none_image_data


class PostJsonDate:
    def __init__(self, index:Dict, postid: str, new_file_name:str):
        self.new_file_name: str = new_file_name
        self.json_builder = JsonBuilder(index, postid)
        
    async def get_json_data(self) -> str:
        return await self.json_builder.build_translated_json()

    async def save_json_file_to_folder(self, file_path: Path, folder_path:str) -> None:
        logger.info(f"Saving JSON to {file_path}")
        path = file_path.parent
        json_path = path / f"{self.new_file_name}.json"
        json_data = await self.get_json_data()
        try:
            async with aiofiles.open(json_path, 'wb') as f:
                await f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))
            logger.info(f"Saved JSON to {json_path}")
        except Exception as e:
            logger.error(f"Failed to save JSON to {json_path}: {e}")


class make_html:
    
    created_folders = set()
    
    def __init__(self, post_media: Dict[str, Any], folder_path: Path, image_list: List[str: URL], new_file_name:str):
        self.new_file_name: str = new_file_name
        self.folder_path: Path = folder_path
        self.image_list: List[str: URL] = image_list
        self.post_media: Dict[str, Any] = post_media

    async def process_html(self, TYPE:bool):
        logger.info("Generating HTML...")
        communityId = self.post_media['communityId']
        title = self.post_media['title']
        body = self.post_media['index']['post']['body']
        time = self.post_media['publishedAt']
        artis = self.post_media['writer_name']
        html_body = self.make_body(TYPE, body)
        avatar_link = await ArtisManger(communityId).get_artis_avatar(artis)
        await SaveHTML(title, time, html_body, artis, self.folder_path, avatar_link, self.new_file_name).update_template_file()

    def make_body(self, TYPE: bool, body: str) -> str:
        if TYPE is True:
            html_parts = [f"<p>{body}</p><br>"]
            html_parts += [f'<p><img src="{url}"></p><br>' for url in self.image_list]
            return ''.join(html_parts)
        else:
            return f"<p>{body}</p>"


async def run_post_dl(selected_media: List[Dict]):
    """
    一次性接收全部selected_media資料，用迴圈處理每一筆
    使用semaphore控制並發數量
    """
    if not selected_media:
        return []
    logger.debug(selected_media)
    semaphore = asyncio.Semaphore(41)
    results = []
    async def process_media_with_limit(media):
        """內部函數：用semaphore控制單筆資料處理"""
        folder = None
        async with semaphore:
            try:
                if media is None:
                    return False
                    
                folder = await FolderManager(media).create_folder()
                make_html.created_folders.add(folder)
                await MainProcessor(media, folder).parse_and_download()
                return True
            except asyncio.CancelledError:
                await handle_cancel(folder)
                return False
            except Exception as e:
                if folder and await aiofiles.os.path.exists(folder):
                    shutil.rmtree(folder, ignore_errors=True)
                logger.exception(f"Error processing media: {e}")
                return False
    # TASK APPEND
    try:
        tasks = [asyncio.create_task(process_media_with_limit(media)) 
                 for media in selected_media]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    except Exception as e:
        # 只在整體失敗時清理所有資料夾
        for folder_path in make_html.created_folders:
            if folder_path and os.path.isdir(folder_path):
                shutil.rmtree(folder_path, ignore_errors=True)
        logger.exception(f"Unexpected error during download: {e}")
        return []


async def handle_cancel(folder: str) -> None:
    try:
        if folder and await aiofiles.os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)
            logger.info(f"Removed partial file: {folder}")
    except OSError as e:
        logger.warning(f"Failed to remove file {folder}: {e}")
        

class File_date_time_formact:
    def __init__(self, folder_name: str, video_meta: dict) -> str:
        self.video_meta = video_meta
        self.folder_name = folder_name
        self.drn = CFG['Donwload_Dir_Name']['dir_name']
        self.oldfmt = CFG['Donwload_Dir_Name']['date_formact']
        self.newfmt = CFG['output_template']['date_formact']
        self.dt_str = self.video_meta.get("date", "")
        
    def new_dt(self) -> str:
        dt: datetime = datetime.strptime(self.dt_str, self.oldfmt)
        d:str = dt.strftime(self.newfmt)
        return d
    
    def new_file_name(self) -> str:
        new_dt = self.new_dt()
        video_meta: Dict[str, str] = {
            "date": new_dt,
            "title": self.video_meta.get("title", ""),
            "community_name": self.video_meta.get("community_name", ""),
            "artis": self.video_meta.get("artis", ""),
            "source": "Berriz",
            "tag": CFG['output_template']['tag']
        }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        return folder_name