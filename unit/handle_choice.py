from lib.media_queue import MediaQueue
from static.color import Color
from cookies.cookies import Berriz_cookie
from unit.berriz_drm import logger
from unit.http.request_berriz_api import My
from unit.GetMediaList import MediaFetcher
from unit.user_choice import InquirerPySelector
from unit.media_json_process import MediaJsonProcessor
from unit.main_process import MediaProcessor

async def handle_choice(community_id: int):
    
    await request_my()
    
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


async def request_my():
    
    if Berriz_cookie()._cookies == {}:
        return
    
    data = await My().fetch_my()
    locat = await My().fetch_location()
    notif = await My().notifications()
    me_data = await My().fetch_me()
    
    join_community = notif['data']['contents']
    
    location = locat['data']['countryCode']
    
    my_id = data['data']['memberInfo']['memberKey']
    my_email = data['data']['memberInfo']['memberEmail']
    memberKey = me_data['data']['memberKey']
    email = me_data['data']['email']
    passwordRegistered = me_data['data']['passwordRegistered']
    passwordMismatchCount = me_data['data']['passwordMismatchCount']
    status = me_data['data']['status']
    createdAt = me_data['data']['createdAt']
    updatedAt = me_data['data']['updatedAt']
    
    logger.info(
        f"{Color.fg('royal_blue')}Login to: {Color.fg('crimson')}{my_id}{Color.reset()}"
        f"{Color.fg('royal_blue')} Mail: {Color.fg('periwinkle')}{my_email}{Color.reset()}"
        f"{Color.fg('royal_blue')} -> {Color.fg('amber')}{location}{Color.reset()}"
        f"{Color.fg('royal_blue')} -> {Color.fg('khaki')}\n[{memberKey} {Color.fg('lavender')}{email} {Color.fg('lemon')}{passwordRegistered} "
        f"{Color.fg('chocolate')}{passwordMismatchCount}"
        f" {status} {Color.fg('periwinkle')}{createdAt} {Color.fg('indigo')}{updatedAt}]{Color.reset()}"
                )
    keys = [i["communityKey"] for i in join_community if i.get("communityKey") not in [None, 'None']]
    if keys:
        logger.info(f"{Color.fg('gray')}My join community: {Color.fg('pink')}{' | '.join(keys)}")

    