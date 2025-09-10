import asyncio

from lib.media_queue import MediaQueue
from mystate.parse_my import request_my
from static.color import Color
from unit.GetMediaList import MediaFetcher
from unit.handle_log import setup_logging
from unit.main_process import MediaProcessor
from unit.media_json_process import MediaJsonProcessor
from unit.user_choice import InquirerPySelector


logger = setup_logging('handle_choice', 'light_slate_gray')


async def handle_choice(community_id: int, time_a, time_b):
    
    await request_my()

    if time_a is not None or time_b is not None:
        logger.info(f"{Color.fg('tomato')}choese "
                    f"{Color.fg('sand')}{time_a} "
                    f"{Color.fg('light_gray')}~"
                    f"{Color.fg('sand')}{time_b}{Color.reset()}"
                    )
    try:
        vod_list, photo_list, live_list = await asyncio.create_task(MediaFetcher(community_id).get_all_media_lists(time_a, time_b))
    except TypeError:
        return
    
    selector = InquirerPySelector(vod_list, photo_list, live_list)
    selected_media = await selector.run()

    if len(selected_media['vods']) > 0:
        logger.info(f"{Color.fg('light_gray')}choese "
            f"{Color.fg('indigo')}{len(selected_media['vods'])} "
            f"{Color.fg('light_gray')}VOD{Color.reset()}")

    if len(selected_media['photos']) > 0:
        logger.info(f"{Color.fg('light_gray')}choese "
                    f"{Color.fg('dark_magenta')}{len(selected_media['photos'])} "
                    f"{Color.fg('light_gray')}PHOTO{Color.reset()}")
        
    if len(selected_media['lives']) > 0:
        logger.info(f"{Color.fg('light_gray')}choese "
                    f"{Color.fg('dark_magenta')}{len(selected_media['lives'])} "
                    f"{Color.fg('light_gray')}Live{Color.reset()}")

    # Process VOD items
    if selected_media['vods']:
        vod_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        vod_queue.enqueue_batch(processed_media["vods"])
        await MediaProcessor().process_media_queue(vod_queue, selected_media)
        
    # Process Live-replay items
    if selected_media['lives']:
        live_replay_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        live_replay_queue.enqueue_batch(processed_media["lives"])
        await MediaProcessor().process_media_queue(live_replay_queue, selected_media)

    # Process PHOTO items
    if selected_media['photos']:
        photo_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        photo_queue.enqueue_batch(processed_media["photos"])
        await MediaProcessor().process_media_queue(photo_queue, selected_media)

    return selected_media



    