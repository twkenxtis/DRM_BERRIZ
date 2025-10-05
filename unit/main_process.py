import asyncio
import os
import sys
from functools import lru_cache
from typing import Any, Awaitable, Callable, Dict, List, Tuple
from pathlib import Path

import aiofiles
import yaml

from lib.lock_cookie import cookie_session
from lib.media_queue import MediaQueue
from lock.donwnload_lock import UUIDSetStore
from static.color import Color
from static.parameter import paramstore
from unit.media.berriz_drm import BerrizProcessor
from unit.handle.handle_log import setup_logging
from unit.image.image import IMGmediaDownloader
from unit.notice.notice import RunNotice
from unit.post.post import run_post_dl


logger = setup_logging('main_process', 'light_peach')


class DuplicateConfig:
    path: Path = Path("config") / "berrizconfig.yaml"
    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, path: str) -> Tuple[bool, bool, bool, bool]:
        return asyncio.run(cls._read_config(path))

    @staticmethod
    async def _read_config(path: str) -> Tuple[bool, bool, bool, bool]:
        if not os.path.exists(path):
            logger.error(f"Config not found: {path}")
            sys.exit(1)

        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            raw = await f.read()

        try:
            cfg = yaml.safe_load(raw)
            overrides = cfg['duplicate']['overrides']
            image_dup = bool(overrides.get('image', False))
            video_dup = bool(overrides.get('video', False))
            post_dup = bool(overrides.get('post', False))
            notice_dup = bool(overrides.get('notice', False))
            return image_dup, video_dup, post_dup, notice_dup
        except (KeyError, yaml.YAMLError) as e:
            logger.error(f"Error parsing {path}: {e}")
            sys.exit(1)

    @classmethod
    def get_image_dup(cls) -> bool:
        return cls.load(DuplicateConfig.path)[0]

    @classmethod
    def get_video_dup(cls) -> bool:
        return cls.load(DuplicateConfig.path)[1]

    @classmethod
    def get_post_dup(cls) -> bool:
        return cls.load(DuplicateConfig.path)[2]

    @classmethod
    def get_notice_dup(cls) -> bool:
        return cls.load(DuplicateConfig.path)[3]


image_dup = DuplicateConfig.get_image_dup()
video_dup = DuplicateConfig.get_video_dup()
post_dup = DuplicateConfig.get_post_dup()
notice_dup = DuplicateConfig.get_notice_dup()

logger.info(
    f"Loaded duplicates → "
    f"{Color.fg('coral')}image: {image_dup}, video: {video_dup}, post: {post_dup}, notice: {notice_dup}"
    f"{Color.reset()}"
)

class MediaProcessor:
    """A class to process media items from a queue, handling VOD and photo items."""

    # 為了精確標記非同步處理函式，定義 ProcessorFunc 類型別名
    ProcessorFunc = Callable[[Any, Any], Awaitable[None]]

    def __init__(self, selected_media: dict[str, Any]) -> None:
        """Initialize the MediaProcessor with a UUIDSetStore."""
        self.store: UUIDSetStore = UUIDSetStore()
        self.selected_media = selected_media
        # 實例變數的類型提示
        self.media_processors: Dict[str, MediaProcessor.ProcessorFunc] = {
            "VOD": self._process_vod_items,
            "LIVE": self._process_vod_items,
            "PHOTO": self._process_photo_items,
            "POST": self._process_post_items,
            "NOTICE": self._process_notice_items,
        }

    def cookie_check(self, media_ids: List[str]) -> bool:
        if cookie_session == {} and paramstore.get('no_cookie') is True:
            logger.warning(f"{Color.fg('light_gray')}Cookies is required to download {Color.bg('crimson')}videos{Color.reset()}")
            logger.info(f"{Color.fg('gold')}Skip {media_ids} video download{Color.reset()}")
            return False
        elif cookie_session == {}:
            raise ValueError('Fail to get cookie correct')
        else:
            return True

    def print_process_items(self, media_ids: List[str], item_name: str) -> None:
        if len(media_ids) < 14:
            logger.info(
                f"{Color.fg('light_gray')}Processing {item_name} IDs:{Color.reset()} {Color.fg('periwinkle')}{media_ids}{Color.reset()} "
                f"{Color.fg('light_gray')}Count:{Color.reset()} {Color.fg('spring_green')}{len(media_ids)}{Color.reset()}"
                )
        else:
            logger.info(
                f"{Color.fg('light_gray')}Processing {item_name} IDs:{Color.reset()} {Color.fg('periwinkle')}{media_ids[-13:]} ...{Color.reset()} "
                f"{Color.fg('light_gray')}Count:{Color.reset()} {Color.fg('spring_green')}{len(media_ids)}{Color.reset()}"
                )

    def add_to_duplicate(self, ids: List[str]):
        for x in ids:
            x = str(x)
            self.store.add(x)

    async def _process_vod_items(self, media_ids: List[Tuple[str, str]]) -> None:
        """Process VOD items using BerrizProcessor."""
        match paramstore.get('key'):
            case True:
                self.print_process_items(media_ids, media_ids[0][1])
                tasks = [
                    asyncio.create_task(
                        BerrizProcessor(media_id, media_type, self.selected_media).run()
                    )
                    for media_id, media_type in media_ids
                ]
                await asyncio.gather(*tasks)
            case None:
                media_id_list = []
                for media_id, media_type in media_ids:
                    media_id_list.append(media_id)
                    self.print_process_items(media_ids, media_type)
                    skip_media_id = await self._check_download_pkl(media_id)
                    if skip_media_id:
                        await self._handle_choice(skip_media_id)
                        continue
                    if self.cookie_check(media_ids):
                        processor: BerrizProcessor = BerrizProcessor(media_id, media_type, self.selected_media)
                        await processor.run()
                if video_dup is False and paramstore.get('key') is None:
                    self.add_to_duplicate(media_id_list)

    async def _process_photo_items(self, media_ids: List[str]) -> None:
        """Process a list of photo items concurrently."""
        try:
            self.print_process_items(media_ids, 'Photo')
            # Assuming run_image_dl can handle a list of media_ids
            await IMGmediaDownloader().run_image_dl(media_ids)
            if image_dup is False:
                self.add_to_duplicate(media_ids)
        except Exception as e:
            logger.error(f"Error processing Photo IDs {media_ids}: {e}")

    async def _process_post_items(self, post_ids: List[str]) -> None:
        """Process a list of photo items concurrently."""
        try:
            self.print_process_items(post_ids, 'Post')
            # Assuming run_post_dl can handle a list of post_ids
            await run_post_dl(self.selected_media['post'])
            if post_dup is False:
                self.add_to_duplicate(post_ids)
        except Exception as e:
            logger.error(f"Error processing Post IDs {post_ids}: {e}")

    async def _process_notice_items(self, notice_ids: List[str]) -> None:
        """Process a list of photo items concurrently."""
        try:
            self.print_process_items(notice_ids, 'Notice')
            # Assuming run_notice_dl can handle a list of notice_ids
            await RunNotice(self.selected_media['notice']).run_notice_dl()
            if notice_dup is False:
                self.add_to_duplicate(notice_ids)
        except Exception as e:
            logger.error(f"Error processing Notice IDs {notice_ids}: {e}")

    async def _check_download_pkl(self, media_id: str | int) -> str | None:
        """Check if media_id exists in the store."""
        media_id_str = str(media_id)
        
        # 如果任何一個重複檢查為 False 且存在於 store 中，則返回 media_id
        if any(dup is False for dup in [image_dup, video_dup, post_dup, notice_dup]) and self.store.exists(media_id_str):
            return media_id_str
        
        return None

    async def _handle_choice(self, skip_media_id: str) -> None:
        """Handle skipping media from 'vods' and 'photos' 'lives' 'post' 'notice' that already exist."""
        for media_type in ("vods", "photos", 'lives', "post", "notice"):
            for item in self.selected_media.get(media_type, []):
                if str(item.get("mediaId")) == skip_media_id or item.get("postId") == skip_media_id:
                    title: str = item.get("title", "Unknown Title")
                    logger.info(f"{Color.bg('crimson')}Already exists{Color.reset()}{Color.fg('light_gray')}, skip download.{Color.reset()}{Color.bg('amber')} {title}{Color.reset()}")
                    return

    async def process_media_queue(
        self, media_queue: MediaQueue
    ) -> None:
        """Process all items in the media queue, batching PHOTO items for concurrent processing."""
        live_ids: List[str] = []  # Temporary list to collect MEDIA media IDs
        post_ids: List[str] = []  # Temporary list to collect POST media IDs
        photo_ids: List[str] = []  # Temporary list to collect PHOTO media IDs
        notice_ids: List[str] = []  # Temporary list to collect NOTICE media IDs
        tasks: List[asyncio.Task] = []  # List to collect async tasks

        while not media_queue.is_empty():
            item: Tuple[str, str] | None = media_queue.dequeue()
            media_id: str
            media_type: str
            media_id, media_type = item
            skip_media_id: str | None = await self._check_download_pkl(media_id) if await self.check_duplicate(media_type) else None
            
            if skip_media_id:
                await self._handle_choice(skip_media_id)
                continue
            
            if media_type == "PHOTO":
                photo_ids.append(media_id)  # Collect PHOTO media IDs
            elif media_type in("VOD", "LIVE"):
                live_ids.append((media_id, media_type))
            elif media_type == "POST":
                post_ids.append(media_id)  # Collect POST media IDs
            elif media_type == "NOTICE":
                notice_ids.append(media_id)  # Collect POST media IDs

        # Process all collected VOD/LIVE media IDs concurrently
        if live_ids and self.cookie_check(live_ids) is True:
            task: asyncio.Task = asyncio.create_task(self._process_vod_items(live_ids))
            tasks.append(task)
        # Process all collected PHOTO media IDs concurrently
        elif photo_ids:
            task: asyncio.Task = asyncio.create_task(self._process_photo_items(photo_ids))
            tasks.append(task)
        # Process all collected POST media IDs concurrently
        elif post_ids:
            task: asyncio.Task = asyncio.create_task(self._process_post_items(post_ids))
            tasks.append(task)
        # Process all collected NOTICE media IDs concurrently
        elif notice_ids:
            task: asyncio.Task = asyncio.create_task(self._process_notice_items(notice_ids))
            tasks.append(task)

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks)

    async def check_duplicate(self, media_type: str) -> bool:
        if image_dup is False and media_type == "PHOTO":
            return True
        elif video_dup is False and media_type == "VOD" and paramstore.get('key') is None:
            return True
        elif post_dup is False and media_type == "POST":
            return True
        elif notice_dup is False and media_type == "NOTICE":
            return True
        return False