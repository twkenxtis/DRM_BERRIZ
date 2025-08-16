import logging

import json

from unit.berriz_drm import *
from unit.image.image import run_image_dl
from lib.media_queue import MediaQueue
from lock.donwnload_lock import UUIDSetStore
from static.color import Color


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger("main_process")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    logger.propagate = False

    # console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # rotating file handler
    app_file_handler = TimedRotatingFileHandler(
        filename="logs/main_process.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


logger = setup_logging()

try:
    if os.path.exists("setting.json"):
        logger.info(f"{Color.fg('light_gray')}setting.json found{Color.reset()}")
    else:
        logger.error(f"{Color.bg('light_gray')}setting.json{Color.reset()} not found")
        raise FileNotFoundError("setting.json, It is required.")
    with open("setting.json", "r", encoding="utf-8") as f:
        config = json.load(f)
        image_dup = config['duplicate']['overrides']['image']
        video_dup = config['duplicate']['overrides']['video']
except Exception as e:
    logger.error(f"Error loading config.json: {e}")
    exit(1)

class MediaProcessor:
    """A class to process media items from a queue, handling VOD and photo items."""

    def __init__(self):
        """Initialize the MediaProcessor with a UUIDSetStore."""
        self.store = UUIDSetStore()
        # Define media processors dictionary
        self.media_processors = {
            "VOD": self._process_vod_items,
            "PHOTO": self._process_photo_items,
        }

    async def _process_vod_items(self, media_id: str) -> None:
        """Process VOD items using BerrizProcessor."""
        try:
            logger.info(f"{Color.fg('light_gray')}Processing VOD ID:{Color.reset()} {Color.fg('periwinkle')}{media_id}{Color.reset()}")
            processor = BerrizProcessor(media_id)
            await processor.run()
            if video_dup is False:
                self.store.add(media_id)
            self.store.add(media_id)
        except Exception as e:
            logger.error(f"Error processing VOD ID {media_id}: {e}")

    async def _process_photo_items(self, media_id: str) -> None:
        """Process photo items."""
        try:
            logger.info(f"{Color.fg('light_gray')}Processing Photo ID:{Color.reset()} {Color.fg('periwinkle')}{media_id}{Color.reset()}")
            await run_image_dl(media_id)
            if image_dup is False:
                self.store.add(media_id)
        except Exception as e:
            logger.error(f"Error processing Photo ID {media_id}: {e}")

    def _check_download_pkl(self, media_id: str) -> str | None:
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
        for media_type in ("vods", "photos"):
            for item in selected_media.get(media_type, []):
                if item.get("mediaId") == skip_media_id:
                    title = item.get("title", "Unknown Title")
                    logging.info(f"{Color.bg('crimson')}Already exists{Color.reset()}{Color.fg('light_gray')}, skip download.{Color.reset()}{Color.bg('amber')} {title}{Color.reset()}")
                    return

    async def process_media_queue(
        self, media_queue: MediaQueue, selected_media: dict
    ) -> None:
        """Process all items in the media queue."""
        while not media_queue.is_empty():
            item = media_queue.dequeue()
            if item is None:
                continue

            media_id, media_type = item
            skip_media_id = self._check_download_pkl(media_id)

            if skip_media_id is None:
                if processor := self.media_processors.get(media_type):
                    await processor(media_id)
                else:
                    logger.warning(f"Unknown media type {media_type} for ID {media_id}")
            else:
                await self._handle_choice(selected_media, skip_media_id)
