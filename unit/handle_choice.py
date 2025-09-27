import asyncio

from lib.artis.artis_menu import Board
from lib.media_queue import MediaQueue
from mystate.parse_my import request_my
from static.color import Color
from unit.GetMediaList import MediaFetcher
from unit.handle_log import setup_logging
from unit.main_process import MediaProcessor
from unit.media_json_process import MediaJsonProcessor
from unit.user_choice import InquirerPySelector
from unit.GetNotifyList import NotifyFetcher
from unit.parameter import paramstore


logger = setup_logging('handle_choice', 'light_slate_gray')


async def fetch_filtered_media(community_id, time_a, time_b):
    # Fetch all media lists concurrently
    vod_list, photo_list, live_list = await asyncio.create_task(
        MediaFetcher(community_id).get_all_media_lists(time_a, time_b)
    )
    post_list = await Board(community_id, time_a, time_b).get_artis_board_list()

    # Get the parameter flags with default False
    liveonly = paramstore.get('liveonly')
    mediaonly = paramstore.get('mediaonly')
    photoonly = paramstore.get('photoonly')
    boardonly = paramstore.get('board')

    # Count how many conditions are True
    active_conditions = sum([liveonly, mediaonly, photoonly, boardonly])

    # If no conditions are True, return all lists
    if active_conditions == 0:
        return vod_list, photo_list, live_list, post_list

    # Initialize result lists based on corresponding flags
    result_vod_list = vod_list if mediaonly else []
    result_photo_list = photo_list if photoonly else []
    result_live_list = live_list if liveonly else []
    result_post_list = post_list if boardonly else []

    return result_vod_list, result_photo_list, result_live_list, result_post_list

async def handle_choice(community_id: int, time_a, time_b):
    
    if paramstore.get('no_cookie') is not True:
        await request_my()

    if time_a is not None or time_b is not None:
        logger.info(f"{Color.fg('tomato')}choese "
                    f"{Color.fg('sand')}{time_a} "
                    f"{Color.fg('light_gray')}- "
                    f"{Color.fg('sand')}{time_b}{Color.reset()}"
                    )
    try:
        vod_list, photo_list, live_list, post_list = await fetch_filtered_media(community_id, time_a, time_b)
        if paramstore.get('notify_mod') is True:
            # notify_only
            live_list = await NotifyFetcher().get_all_notify_lists(time_a, time_b)
            vod_list, photo_list, post_list = [], [], []

    except TypeError as e:
        logger.error(e)
        return
    selector = InquirerPySelector(vod_list, photo_list, live_list, post_list)
    selected_media = await selector.run()
    
    if selected_media is None:
        logger.info(f"{Color.fg('light_gray')}No items selected. Exiting...{Color.reset()}")
        return
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
        
    if len(selected_media['post']) > 0:
        logger.info(f"{Color.fg('light_gray')}choese "
                    f"{Color.fg('dark_magenta')}{len(selected_media['post'])} "
                    f"{Color.fg('light_gray')}Post{Color.reset()}")

    # Process VOD items
    if selected_media['vods']:
        vod_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        vod_queue.enqueue_batch(processed_media["vods"], 'VOD')
        await MediaProcessor().process_media_queue(vod_queue, selected_media)
        
    # Process Live-replay items
    if selected_media['lives']:
        live_replay_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        live_replay_queue.enqueue_batch(processed_media["lives"], 'LIVE')
        await MediaProcessor().process_media_queue(live_replay_queue, selected_media)

    # Process PHOTO items
    if selected_media['photos']:
        photo_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        photo_queue.enqueue_batch(processed_media["photos"], 'PHOTO')
        await MediaProcessor().process_media_queue(photo_queue, selected_media)

    # Process POST items
    if selected_media['post']:
        post_queue = MediaQueue()
        processed_media = MediaJsonProcessor.process_selection(selected_media)
        post_queue.enqueue_batch(processed_media["post"], 'POST')
        await MediaProcessor().process_media_queue(post_queue, selected_media)

    return selected_media



    