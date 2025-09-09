import aiofiles
import asyncio
import orjson
import os
import sys
from functools import lru_cache

from typing import List

from cookies.cookies import Berriz_cookie
from unit.berriz_drm import BerrizProcessor
from unit.image.image import run_image_dl
from lib.media_queue import MediaQueue
from lock.donwnload_lock import UUIDSetStore
from static.color import Color
from unit.handle_log import setup_logging
from unit.parameter import paramstore


logger = setup_logging('main_process', 'navy')


class DuplicateConfig:
    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, path: str) -> tuple[str, str]:
        return asyncio.run(cls._read_config(path))

    @staticmethod
    async def _read_config(path: str) -> tuple[str, str]:
        if not os.path.exists(path):
            logger.error(f"Config not found: {path}")
            sys.exit(1)

        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            raw = await f.read()

        try:
            cfg = orjson.loads(raw)
            overrides = cfg['duplicate']['overrides']
            image_dup = overrides['image']
            video_dup = overrides['video']
            return image_dup, video_dup
        except (KeyError, orjson.JSONDecodeError) as e:
            logger.error(f"Error parsing {path}: {e}")
            sys.exit(1)

    @classmethod
    def get_image_dup(cls, path: str = "setting.json") -> str:
        """Return the cached image duplicate override."""
        return cls.load(path)[0]

    @classmethod
    def get_video_dup(cls, path: str = "setting.json") -> str:
        """Return the cached video duplicate override."""
        return cls.load(path)[1]


image_dup = DuplicateConfig.get_image_dup("setting.json")
video_dup = DuplicateConfig.get_video_dup("setting.json")
logger.info(f"Loaded duplicates → image: {image_dup}, video: {video_dup}")


class MediaProcessor:
    """A class to process media items from a queue, handling VOD and photo items."""

    def __init__(self):
        """Initialize the MediaProcessor with a UUIDSetStore."""
        self.store = UUIDSetStore()
        self.media_processors = {
            "VOD": self._process_vod_items,
            "LIVE": self._process_vod_items,
            "PHOTO": self._process_photo_items,
        }

    async def _process_vod_items(self, media_id: str, media_type) -> None:
        """Process VOD items using BerrizProcessor."""
        if len(Berriz_cookie()._cookies) == 0:
            logger.warning(f"{Color.fg('light_gray')}Cookies are required to download {Color.bg('crimson')}videos{Color.reset()}")
            logger.info(f"{Color.fg('gold')}Skip {media_id} video download{Color.reset()}")
            return
        logger.info(f"{Color.fg('light_gray')}Processing VOD ID:{Color.reset()} {Color.fg('periwinkle')}{media_id}{Color.reset()}")
        processor = BerrizProcessor(media_id, media_type)
        await processor.run()
        if video_dup is False and paramstore.get('key') is None:
            self.store.add(media_id)

    async def _process_photo_items(self, media_ids: List[str]) -> None:
        """Process a list of photo items concurrently."""
        try:
            if len(media_ids) < 14:
                logger.info(f"{Color.fg('light_gray')}Processing Photo IDs:{Color.reset()} {Color.fg('periwinkle')}{media_ids}{Color.reset()}")
            else:
                logger.info(f"{Color.fg('light_gray')}Processing Photo IDs:{Color.reset()} {Color.fg('periwinkle')}{media_ids[-13:]} ...{Color.reset()}")
            # Assuming run_image_dl can handle a list of media_ids
            await run_image_dl(media_ids)
            if image_dup is False:
                for media_id in media_ids:
                    self.store.add(media_id)
        except Exception as e:
            logger.error(f"Error processing Photo IDs {media_ids}: {e}")

    async def _check_download_pkl(self, media_id: str) -> str | None:
        """Check if media_id exists in the store."""
        if image_dup is False:
            if self.store.exists(media_id):
                return media_id
        if video_dup is False:
            if self.store.exists(media_id):
                return media_id
        return None

    async def _handle_choice(self, selected_media: dict, skip_media_id: str) -> None:
        """Handle skipping media from 'vods' and 'photos' that already exist."""
        for media_type in ("vods", "photos", 'lives'):
            for item in selected_media.get(media_type, []):
                if item.get("mediaId") == skip_media_id:
                    title = item.get("title", "Unknown Title")
                    logger.info(f"{Color.bg('crimson')}Already exists{Color.reset()}{Color.fg('light_gray')}, skip download.{Color.reset()}{Color.bg('amber')} {title}{Color.reset()}")
                    return

    async def process_media_queue(
        self, media_queue: MediaQueue, selected_media: dict
    ) -> None:
        """Process all items in the media queue, batching PHOTO items for concurrent processing."""
        photo_ids = []  # Temporary list to collect PHOTO media IDs
        tasks = []  # List to collect async tasks

        while not media_queue.is_empty():
            item = media_queue.dequeue()
            if item is None:
                continue
            media_id, media_type = item
            skip_media_id = await self._check_download_pkl(media_id) if await self.check_duplicate(media_type) else None

            if skip_media_id:
                await self._handle_choice(selected_media, skip_media_id)
                continue

            if media_type == "PHOTO":
                photo_ids.append(media_id)  # Collect PHOTO media IDs
            else:
                if processor := self.media_processors.get(media_type):
                    await processor(media_id, media_type)
                else:
                    logger.warning(f"Unknown media type {media_type} for ID {media_id}")

        # Process all collected PHOTO media IDs concurrently
        if photo_ids:
            task = asyncio.create_task(self._process_photo_items(photo_ids))
            tasks.append(task)

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks)

    async def check_duplicate(self, media_type: str) -> bool:
        if image_dup is False and media_type == "PHOTO":
            return True
        if video_dup is False and media_type == "VOD" and paramstore.get('key') is None:
            return True
        return False