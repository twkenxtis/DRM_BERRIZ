import asyncio
import random
import string
import os
from itertools import islice
from pathlib import Path

from typing import Any, Dict, List, Tuple, Optional

import aiofiles
import orjson

from mystate.fanclub import fanclub_main
from unit.handle_board_from import JsonBuilder
from unit.image.class_ImageDownloader import ImageDownloader
from unit.community import custom_dict, get_community
from unit.handle_log import setup_logging


logger = setup_logging('post', 'maroon')


class FolderManager:
    """管理下載的資料夾創建"""
    def __init__(self):
        self._lock = asyncio.Lock()

    async def create_folder(self, folder_name: str, community_id: int, board_name: str) -> Optional[str]:
        raw_name = await self.get_community_name(community_id)
        community = self._sanitize_name(raw_name)
        base_dir = Path.cwd() / "downloads" / community / board_name

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
    def _sanitize_name(raw: Optional[str]) -> str:
        """將 None、空字串或特殊字元過濾成合法資料夾名，並套用 custom_dict 映射"""
        if not raw:
            return "unknown_community"

        mapped = custom_dict(raw)
        if mapped is not None:
            raw = mapped

        # 過濾非法字元
        cleaned = "".join(c for c in raw if c.isalnum() or c in "-_ ")
        return cleaned.strip()

    async def get_community_name(self, community_id: int) -> Optional[str]:
        n = await get_community(community_id)
        return n


class MainProcessor:
    """Parses image URLs and manages their download."""
    def __init__(self, post_media: Dict):
        self.post_media = post_media
        self.post_id = post_media["postId"]
        self.json_data_obj = PostJsonDate(self.post_media['index'], self.post_id)

    async def parse_and_download(self, folder: str) -> None:
        """Parse image URLs and download them with concurrency control."""
        folder_path = Path(folder)
        image_data, none_image_data = self.filter_post_data()

        try:
            async with asyncio.TaskGroup() as tg:
                if image_data:
                    tg.create_task(self.process(image_data, folder_path, True))
                else:
                    tg.create_task(self.process(self.post_media, folder_path, False))
        except* Exception as eg:
            for exc in eg.exceptions:
                logger.error(f"Error during parse_and_download: {exc}")
                
    async def process(self, data: List[Dict[str, Any]], folder_path: Path, TYPE:bool) -> None:
        if TYPE is True:
            for idx, image in enumerate(data[1]):
                if not image:
                    logger.error('Not url: ', image)
                    continue
                name = Path(image).name or f"image_{idx}.jpg"
                name = name.split("?")[0]
                file_path = folder_path / name
                await ImageDownloader.download_image(image, file_path)
        elif TYPE is False:
            for i in data:
                file_path = folder_path / 'none-image-media'
        await self.json_data_obj.save_json_file_to_folder(file_path, folder_path)

    def filter_post_data(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        image_data, none_image_data = [], []

        for item in self.post_media['imageInfo']:
            if isinstance(item, (list, tuple)) and any(item):
                image_data.append(item)
            else:
                none_image_data.append(item)
        return image_data, none_image_data


class PostJsonDate:
    def __init__(self, index:Dict, postid: str):
        self.json_builder = JsonBuilder(index, postid)
        
    async def get_json_data(self) -> str:
        return await self.json_builder.build_translated_json()

    async def save_json_file_to_folder(self, file_path: Path, folder_path:str) -> None:
        path = file_path.parent
        json_path = path / f"{folder_path.name}.json"
        json_data = await self.get_json_data()
        try:
            async with aiofiles.open(json_path, 'wb') as f:
                await f.write(orjson.dumps(json_data, option=orjson.OPT_INDENT_2))
            logger.info(f"Saved JSON to {json_path}")
        except Exception as e:
            logger.error(f"Failed to save JSON to {json_path}: {e}")

async def run_post_dl(selected_media, max_concurrent: int = 7, chunk_size: int = 10):
    semaphore = asyncio.Semaphore(max_concurrent)
    folder_manager = FolderManager()
    async def process_single_media(post_media: str):
        async with semaphore:
            folder = await folder_manager.create_folder(post_media['folderName'], post_media['communityId'], post_media['board_name'])
            await MainProcessor(post_media).parse_and_download(folder)

    for chunk in chunked_iter(selected_media, chunk_size):
        tasks = [process_single_media(id) for id in chunk]
        # schedule current batch; semaphore also caps in-flight concurrency
        await asyncio.gather(*tasks, return_exceptions=True)

def chunked_iter(iterable, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk