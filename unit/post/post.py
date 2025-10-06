import asyncio
import os
import random
import shutil
import string
from datetime import datetime
from pathlib import Path

from typing import Any, Dict, List, Tuple, Optional, TypedDict

import aiofiles
import orjson
from httpx import URL
from pprint import pprint

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


class Media(TypedDict):
    photo: List
    link: List
    analysis: List

class PostIndex(TypedDict):
    postId: str
    userId: int
    communityId: int
    title: str
    body: str
    plainBody: str
    languageCode: str
    createdAt: str
    updatedAt: str
    isActive: bool
    isBaned: bool
    status: str
    isUpdated: bool
    media: Media
    hashtags: List[str]

class WriterIndex(TypedDict):
    userId: int
    communityId: int
    type: str
    communityArtistId: int
    isArtist: bool
    name: str
    imageUrl: str
    bgImageUrl: str
    isFanclubUser: bool

class CountInfo(TypedDict):
    commentCount: int
    likeCount: int

class BoardInfo(TypedDict):
    boardId: str
    boardType: str
    communityId: int
    name: str
    isFanclubOnly: bool

class Index(TypedDict):
    post: PostIndex
    writer: WriterIndex
    countInfo: CountInfo
    boardInfo: BoardInfo

class VideoMeta(TypedDict):
    date: str
    title: str
    community_name: str
    artis: str
    source: str
    tag: str

class PostData(TypedDict):
    publishedAt: str
    title: str
    mediaType: str
    communityId: int
    isFanclubOnly: bool
    communityName: str
    folderName: str
    timeStr: str
    postId: str
    imageInfo: Tuple[List, List, List, List]
    mediaId: List
    board_name: str
    writer_name: str
    index: Index
    fetcher: object
    video_meta: VideoMeta
    

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
    
    created_folders = set()
    
    """Parses image URLs and manages their download."""
    def __init__(self, post_media: Dict, folder: str):
        self.post_media: PostData = post_media
        self.fetcher: BoardFetcher = post_media['fetcher']
        self.post_id = self.fetcher.get_postid()
        self.folder_path: Path = Path(folder)
        self.FDTF = File_date_time_formact(post_media['folderName'], post_media['video_meta'])
        self.new_file_name = self.FDTF.new_file_name()
        self.json_data_obj = PostJsonDate(self.post_media['index'], self.post_id, self.new_file_name)
        self.communityId: int = self.post_media['communityId']
        self.title: str = self.post_media['title']
        self.body: str = self.post_media['index']['post']['body']
        self.time: str = self.post_media['publishedAt']
        self.artis: str = self.post_media['writer_name']
        self.ArtisManger = ArtisManger(self.communityId)
        self.TYPE: bool = None
        self.image_list: List[URL] = None

    async def parse_and_download(self) -> None:
        """Parse image URLs and download them with concurrency control."""
        image_data, none_image_data = self.filter_post_data()
        if image_data:
            self.TYPE = True
            await self.process_image(image_data)
        elif none_image_data:
            self.TYPE = False
            await asyncio.gather(
            await self.json_data_obj.save_json_file_to_folder(self.folder_path),
            await self.process_and_save([])
            )
                    
    async def process_image(self, data: List[Dict[str, Any]]) -> None:
        if not data or len(data) < 2:
            logger.warning("Invalid or insufficient data provided.")
            return
        if self.TYPE:
            List_images = data[1]
            if not isinstance(data[1], list):
                logger.warning("data[1] is not a list.")
                List_images = []
            await self.download_images_concurrently(List_images)
            await self.process_and_save(List_images)
            
    async def process_and_save(self, image_list: List[URL]) -> None:
        await asyncio.gather(
            self.json_data_obj.save_json_file_to_folder(self.folder_path),
            self.process_html(image_list)
        )

    async def download_images_concurrently(self, image_list: List[URL]) -> None:
        for idx, image in enumerate(image_list):
            try:
                name = Path(str(image)).name or f"image_{idx}.jpg"
                name = name.split("?")[0]
                img_file_path = self.folder_path / name
                logger.debug(f"Downloading: {image} → \n{img_file_path}")
                await ImageDownloader.download_image(image, img_file_path)
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

    async def process_html(self, image_list: List[str: URL]):
        logger.info("Generating HTML...")
        html_body = self.make_body(image_list)
        avatar_link = await self.ArtisManger.get_artis_avatar(self.artis)
        await SaveHTML(self.title, self.time, html_body, self.artis, self.folder_path, avatar_link, self.new_file_name).update_template_file()

    def make_body(self, image_list: List[str: URL]) -> str:
        if self.TYPE is True:
            html_parts = [f"<p>{self.body}</p><br>"]
            html_parts += [f'<p><img src="{url}"></p><br>' for url in image_list]
            return ''.join(html_parts)
        else:
            return f"<p>{self.body}</p>"


class PostJsonDate:
    def __init__(self, index:Dict, postid: str, new_file_name:str):
        self.new_file_name: str = new_file_name
        self.json_builder = JsonBuilder(index, postid)
        
    async def get_json_data(self) -> str:
        return await self.json_builder.build_translated_json()

    async def save_json_file_to_folder(self, file_path: Path) -> None:
        logger.info(f"Saving JSON to {file_path}")
        json_path: Path = file_path / f"{self.new_file_name}.json"
        json_data: Dict[str, Any] = await self.get_json_data()
        try:
            async with aiofiles.open(json_path, 'wb') as f:
                await f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))
            logger.info(f"Saved JSON to {json_path}")
        except Exception as e:
            logger.error(f"Failed to save JSON to {json_path}: {e}")


class Run_Post_dl:
    def __init__(self, selected_media: List[Dict]):
        self.selected_media = selected_media
    
    async def run_post_dl(self):
        semaphore = asyncio.Semaphore(41)
        results = []
        try:
            async def process(index: Dict[str, Any]) -> str:
                folder = None
                async with semaphore:
                    try:
                        folder = await FolderManager(index).create_folder()
                        MainProcessor.created_folders.add(folder)
                        await MainProcessor(index, folder).parse_and_download()
                        return results
                    except asyncio.CancelledError:
                        await self.handle_cancel(folder)
                        return []
            tasks = [asyncio.create_task(process(index)) for index in self.selected_media]
            await asyncio.gather(*tasks)
        except Exception as e:
            # 只在整體失敗時清理所有資料夾
            for folder_path in MainProcessor.created_folders:
                if folder_path and os.path.isdir(folder_path):
                    shutil.rmtree(folder_path, ignore_errors=True)
            logger.exception(f"Unexpected error during download: {e}")
            return []

    async def handle_cancel(self, folder: str) -> None:
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