import asyncio

from lib.media_queue import MediaQueue
from static.color import Color
from cookies.cookies import Berriz_cookie
from unit.berriz_drm import logger
from unit.http.request_berriz_api import My
from unit.GetMediaList import MediaFetcher
from unit.user_choice import InquirerPySelector
from unit.media_json_process import MediaJsonProcessor
from unit.main_process import MediaProcessor

async def handle_choice(community_id: int, time_a, time_b):
    
    await request_my()

    if time_a is not None or time_b is not None:
        logger.info(f"{Color.fg('tomato')}choese "
                    f"{Color.fg('sand')}{time_a} "
                    f"{Color.fg('light_gray')}~"
                    f"{Color.fg('sand')}{time_b}{Color.reset()}"
                    )

    vod_list, photo_list, live_list = await asyncio.create_task(MediaFetcher(community_id).get_all_media_lists(time_a, time_b))
    if not vod_list and not photo_list:
        logger.warning("No media items found")
        return None
    
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

    if len(selected_media['live']) > 0:
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


async def request_my():
    # 檢查 cookie，若無則直接返回
    if not Berriz_cookie()._cookies:
        return

    try:
        data, locat, notif, me_data = await asyncio.gather(
            My().fetch_my(),
            My().fetch_location(),
            My().notifications(),
            My().fetch_me()
        )

        # 提取資料並使用 .get() 方法，以避免 KeyError
        my_id = data.get('data', {}).get('memberInfo', {}).get('memberKey')
        my_email = data.get('data', {}).get('memberInfo', {}).get('memberEmail')
        
        location = locat.get('data', {}).get('countryCode')

        me_info = me_data.get('data', {})
        memberKey = me_info.get('memberKey')
        email = me_info.get('email')
        passwordRegistered = me_info.get('passwordRegistered')
        passwordMismatchCount = me_info.get('passwordMismatchCount')
        status = me_info.get('status')
        createdAt = me_info.get('createdAt')
        updatedAt = me_info.get('updatedAt')

        # 提取社羣金鑰
        join_community = notif.get('data', {}).get('contents', [])
        keys = [i.get("communityKey") for i in join_community if i.get("communityKey")]
        
        logger.info(
            f"{Color.fg('royal_blue')}Login to: {Color.fg('crimson')}{my_id}{Color.reset()}"
            f" {Color.fg('royal_blue')}Mail: {Color.fg('periwinkle')}{my_email}{Color.reset()}"
            f" {Color.fg('royal_blue')}-> {Color.fg('amber')}{location}{Color.reset()}"
            f" {Color.fg('royal_blue')}-> {Color.fg('khaki')}\n[{memberKey} {Color.fg('lavender')}{email} {Color.fg('lemon')}{passwordRegistered} "
            f"{Color.fg('chocolate')}{passwordMismatchCount}"
            f" {status} {Color.fg('periwinkle')}{createdAt} {Color.fg('indigo')}{updatedAt}]{Color.reset()}"
        )

        if keys:
            logger.info(f"{Color.fg('gray')}My joined communities: {Color.fg('pink')}{' | '.join(keys)}")
            
    except Exception as e:
        logger.error(f"An unexpected error occurred during API requests: {e}")
    