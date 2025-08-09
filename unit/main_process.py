from unit.berriz_drm import *
from unit.image.image import run_image_dl
from lib.media_queue import MediaQueue
from lock.donwnload_lock import UUIDSetStore
import logging

# Configure logger
logger = logging.getLogger(__name__)


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
            logger.info(f"Processing VOD ID: {media_id}")
            processor = BerrizProcessor(media_id)
            await processor.run()
            self.store.add(media_id)
        except Exception as e:
            logger.error(f"Error processing VOD ID {media_id}: {e}")

    async def _process_photo_items(self, media_id: str) -> None:
        """Process photo items."""
        try:
            logger.info(f"Processing Photo ID: {media_id}")
            await run_image_dl(media_id)
            self.store.add(media_id)
        except Exception as e:
            logger.error(f"Error processing Photo ID {media_id}: {e}")

    def _check_download_pkl(self, media_id: str) -> str | None:
        """Check if media_id exists in the store."""
        if self.store.exists(media_id):
            return media_id
        return None

    async def _handle_choice(self, selected_media: dict, skip_media_id: str) -> None:
        """Handle skipping media from 'vods' and 'photos' that already exist."""
        for media_type in ("vods", "photos"):
            for item in selected_media.get(media_type, []):
                if item.get("mediaId") == skip_media_id:
                    title = item.get("title", "Unknown Title")
                    logger.info(f"{title} Already exists, skip download.")
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
