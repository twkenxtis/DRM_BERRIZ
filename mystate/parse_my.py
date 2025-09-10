import asyncio

from cookies.cookies import Berriz_cookie
from static.color import Color
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import My



logger = setup_logging('parse_my', 'ruby')


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