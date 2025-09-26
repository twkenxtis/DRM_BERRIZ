import asyncio
from functools import lru_cache
import os
import sys
from typing import List

import aiofiles
import orjson

from lib.media_queue import MediaQueue
from lib.lock_cookie import cookie_session
from lock.donwnload_lock import UUIDSetStore
from static.color import Color
from unit.berriz_drm import BerrizProcessor
from unit.handle_log import setup_logging
from unit.image.image import IMGmediaDownloader
from unit.post.post import run_post_dl
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
            post_dup = overrides['post']
            return image_dup, video_dup, post_dup
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

    @classmethod
    def get_post_dup(cls, path: str = "setting.json") -> str:
        """Return the cached post duplicate override."""
        return cls.load(path)[2]


image_dup = DuplicateConfig.get_image_dup("setting.json")
video_dup = DuplicateConfig.get_video_dup("setting.json")
post_dup = DuplicateConfig.get_post_dup("setting.json")
logger.info(f"Loaded duplicates → {Color.fg('coral')}image: {image_dup}, video: {video_dup}, post: {post_dup}{Color.reset()}")


class MediaProcessor:
    """A class to process media items from a queue, handling VOD and photo items."""

    def __init__(self):
        """Initialize the MediaProcessor with a UUIDSetStore."""
        self.store = UUIDSetStore()
        self.media_processors = {
            "VOD": self._process_vod_items,
            "LIVE": self._process_vod_items,
            "PHOTO": self._process_photo_items,
            "POST": self._process_post_items,
        }

    async def _process_vod_items(self, media_id: str, media_type) -> None:
        """Process VOD items using BerrizProcessor."""
        if cookie_session == {} and paramstore.get('no_cookie') is True:
            logger.warning(f"{Color.fg('light_gray')}Cookies is required to download {Color.bg('crimson')}videos{Color.reset()}")
            logger.info(f"{Color.fg('gold')}Skip {media_id} video download{Color.reset()}")
            return
        elif cookie_session == {}:
            raise ValueError('Fail to get cookie correct')

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
            await IMGmediaDownloader().run_image_dl(media_ids)
            if image_dup is False:
                for media_id in media_ids:
                    self.store.add(media_id)
        except Exception as e:
            logger.error(f"Error processing Photo IDs {media_ids}: {e}")

    async def _process_post_items(self, post_ids: List[str], selected_media) -> None:
        """Process a list of photo items concurrently."""
        try:
            if len(post_ids) < 14:
                logger.info(f"{Color.fg('light_gray')}Processing Post IDs:{Color.reset()} {Color.fg('periwinkle')}{post_ids}{Color.reset()}")
            else:
                logger.info(f"{Color.fg('light_gray')}Processing Post IDs:{Color.reset()} {Color.fg('periwinkle')}{post_ids[-13:]} ...{Color.reset()}")
            # Assuming run_post_dl can handle a list of post_ids
            await run_post_dl(selected_media['post'])
            if post_dup is False:
                for post_id in post_ids:
                    self.store.add(post_id)
        except Exception as e:
            logger.error(f"Error processing Post IDs {post_ids}: {e}")

    async def _check_download_pkl(self, media_id: str) -> str | None:
        """Check if media_id exists in the store."""
        if image_dup is False:
            if self.store.exists(media_id):
                return media_id
        if video_dup is False:
            if self.store.exists(media_id):
                return media_id
        if post_dup is False:
            if self.store.exists(media_id):
                return media_id
        return None

    async def _handle_choice(self, selected_media: dict, skip_media_id: str) -> None:
        """Handle skipping media from 'vods' and 'photos' that already exist."""
        for media_type in ("vods", "photos", 'lives', "post"):
            for item in selected_media.get(media_type, []):
                if item.get("mediaId") == skip_media_id:
                    title = item.get("title", "Unknown Title")
                    logger.info(f"{Color.bg('crimson')}Already exists{Color.reset()}{Color.fg('light_gray')}, skip download.{Color.reset()}{Color.bg('amber')} {title}{Color.reset()}")
                    return

    async def process_media_queue(
        self, media_queue: MediaQueue, selected_media: dict
    ) -> None:
        """Process all items in the media queue, batching PHOTO items for concurrent processing."""
        post_ids = []  # Temporary list to collect POST media IDs
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
            elif media_type in("VOD", "LIVE"):
                if processor := self.media_processors.get(media_type):
                    await processor(media_id, media_type)
                else:
                    logger.warning(f"Unknown media type {media_type} for ID {media_id}")
            elif media_type == "POST":
                post_ids.append(media_id)  # Collect POST media IDs

        # Process all collected PHOTO media IDs concurrently
        if photo_ids:
            task = asyncio.create_task(self._process_photo_items(photo_ids))
            tasks.append(task)
        # Process all collected POST media IDs concurrently
        if post_ids:
            task = asyncio.create_task(self._process_post_items(post_ids, selected_media))
            tasks.append(task)

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks)

    async def check_duplicate(self, media_type: str) -> bool:
        if image_dup is False and media_type == "PHOTO":
            return True
        if video_dup is False and media_type == "VOD" and paramstore.get('key') is None:
            return True
        if post_dup is False and media_type == "POST" and paramstore.get('key') is None:
            return True
        return False