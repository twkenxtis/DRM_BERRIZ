from lib.media_queue import MediaQueue
from unit.berriz_drm import logger
from unit.GetMediaList import MediaFetcher, NumericSelector
from unit.media_json_process import MediaJsonProcessor
from unit.main_process import MediaProcessor

async def handle_choice():
    community_id = 7

    media_fetcher = MediaFetcher(community_id=community_id)
    vod_list, photo_list = await media_fetcher.get_all_media_lists()

    if not vod_list and not photo_list:
        logger.warning("No media items found")
        return None

    selector = NumericSelector(vod_list, photo_list, page_size=60)
    selected_media = selector.run()

    if len(selected_media['vods']) > 0:
        print(f"- {len(selected_media['vods'])} VOD")
    if len(selected_media['photos']) > 0:
        print(f"- {len(selected_media['photos'])} PHOTO")

    # Process the selected media and create queue
    media_queue = MediaQueue()
    processed_media = MediaJsonProcessor.process_selection(selected_media)

    # Add all media items to the queue
    media_queue.enqueue_batch(processed_media["vods"])
    media_queue.enqueue_batch(processed_media["photos"])

    # Process all items in the queue
    await MediaProcessor().process_media_queue(media_queue, selected_media)

    return selected_media
