from unit.berriz_drm import *
from unit.image.image import run_image_dl
from lib.media_queue import MediaQueue

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
        await run_image_dl(media_id)
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