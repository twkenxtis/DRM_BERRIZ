import asyncio
import logging
from typing import List, Dict, Any, Optional
from collections import deque
from logging.handlers import TimedRotatingFileHandler

from unit.berriz_drm import *
from unit.GetMediaList import MediaFetcher, NumericSelector


class MediaQueue:
    """A queue class for managing media IDs to be processed."""

    def __init__(self):
        self._queue = deque()
        self._processed_items = set()  # To avoid duplicates

    def enqueue(self, media_id: str, media_type: str) -> None:
        """Add a media ID to the queue if it hasn't been processed yet."""
        if media_id not in self._processed_items:
            self._queue.append((media_id, media_type))
            self._processed_items.add(media_id)

    def enqueue_batch(self, media_items: List[Dict[str, Any]]) -> None:
        """Add multiple media items to the queue."""
        for item in media_items:
            if "mediaId" in item and "mediaType" in item:
                self.enqueue(item["mediaId"], item["mediaType"])

    def dequeue(self) -> Optional[tuple[str, str]]:
        """Remove and return the next media ID and type from the queue."""
        if not self.is_empty():
            return self._queue.popleft()
        return None

    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return len(self._queue) == 0

    def size(self) -> int:
        """Return the current size of the queue."""
        return len(self._queue)


class MediaJsonProcessor:
    """A class for processing JSON media data and extracting relevant information."""

    @staticmethod
    def process_selection(
        selected_media: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Process the selected media dictionary and return categorized media items."""
        processed = {"vods": [], "photos": []}

        # Process VODs
        if "vods" in selected_media and selected_media["vods"]:
            processed["vods"] = [
                item
                for item in selected_media["vods"]
                if "mediaId" in item and "mediaType" in item
            ]

        # Process Photos
        if "photos" in selected_media and selected_media["photos"]:
            processed["photos"] = [
                item
                for item in selected_media["photos"]
                if "mediaId" in item and "mediaType" in item
            ]

        return processed


async def process_vod_items(media_id: str) -> None:
    """Process VOD items using BerrizProcessor."""
    try:
        logger.info(f"Processing VOD ID: {media_id}")
        processor = BerrizProcessor(media_id)
        await processor.run()
    except Exception as e:
        logger.error(f"Error processing VOD ID {media_id}: {e}")


async def process_photo_items(media_id: str) -> None:
    """Process photo items (placeholder for your implementation)."""
    try:
        logger.info(f"Processing Photo ID: {media_id}")
        # Your photo processing implementation will go here
        # For now, just pass as requested
        pass
    except Exception as e:
        logger.error(f"Error processing Photo ID {media_id}: {e}")


async def process_media_queue(media_queue: MediaQueue) -> None:
    """Process all items in the media queue."""
    while not media_queue.is_empty():
        item = media_queue.dequeue()
        if item is None:
            continue

        media_id, media_type = item
        if media_type == "VOD":
            await process_vod_items(media_id)
        elif media_type == "PHOTO":
            await process_photo_items(media_id)
        else:
            logger.warning(f"Unknown media type {media_type} for ID {media_id}")


def setup_logging() -> logging.Logger:
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("main")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "main.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)
    return app_logger


async def handle_choice():
    community_id = 7

    media_fetcher = MediaFetcher(community_id=community_id)
    vod_list, photo_list = await media_fetcher.get_all_media_lists()

    if not vod_list and not photo_list:
        logger.warning("No media items found")
        return None

    selector = NumericSelector(vod_list, photo_list, page_size=60)
    selected_media = selector.run()

    print(f"- {len(selected_media['vods'])} 個 VOD")
    print(f"- {len(selected_media['photos'])} 張照片")

    # Process the selected media and create queue
    media_queue = MediaQueue()
    processed_media = MediaJsonProcessor.process_selection(selected_media)

    # Add all media items to the queue
    media_queue.enqueue_batch(processed_media["vods"])
    media_queue.enqueue_batch(processed_media["photos"])

    # Process all items in the queue
    await process_media_queue(media_queue)

    return selected_media


if __name__ == "__main__":
    logger = setup_logging()
    try:
        final_selection = asyncio.run(handle_choice())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"主程式執行錯誤: {e}", exc_info=True)
