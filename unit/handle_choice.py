from lib.media_queue import MediaQueue
from static.color import Color
from unit.berriz_drm import logger
from unit.GetMediaList import MediaFetcher
from unit.user_choice import InquirerPySelector
from unit.media_json_process import MediaJsonProcessor
from unit.main_process import MediaProcessor

async def handle_choice(community_id: int):
    media_fetcher = MediaFetcher(community_id)
    vod_list, photo_list = await media_fetcher.get_all_media_lists()

    if not vod_list and not photo_list:
        logger.warning("No media items found")
        return None
    
    selector = InquirerPySelector(vod_list, photo_list)
    selected_media = await selector.run()

    if len(selected_media['vods']) > 0:
        logger.info(f"{Color.fg('light_gray')}choese "
            f"{Color.fg('indigo')}{len(selected_media['vods'])} "
            f"{Color.fg('light_gray')}VOD{Color.reset()}")

    if len(selected_media['photos']) > 0:
        logger.info(f"{Color.fg('light_gray')}choese "
                    f"{Color.fg('dark_magenta')}{len(selected_media['photos'])} "
                    f"{Color.fg('light_gray')}PHOTO{Color.reset()}")

    # Process VOD items
    if selected_media['vods']:
        vod_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        vod_queue.enqueue_batch(processed_media["vods"])
        await MediaProcessor().process_media_queue(vod_queue, selected_media)

    # Process PHOTO items
    if selected_media['photos']:
        photo_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        photo_queue.enqueue_batch(processed_media["photos"])
        await MediaProcessor().process_media_queue(photo_queue, selected_media)

    return selected_media

