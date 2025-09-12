import asyncio

from static.color import Color
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import My, BerrizAPIClient


logger = setup_logging('parse_my', 'ruby')


async def request_my():
    # 檢查 cookie，若無則直接返回
    if await retry() is False:
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
            f" {Color.fg('royal_blue')}➤  {Color.fg('amber')}{location}{Color.reset()}"
            f" {Color.fg('royal_blue')}\n[memberKey: {Color.fg('khaki')}{memberKey} {Color.fg('lavender')}{email} "
            f"{Color.fg('royal_blue')}passwordRegistered: {Color.fg('lemon')}{passwordRegistered} "
            f"{Color.fg('royal_blue')}passwordMismatchCount: {Color.fg('chocolate')}{passwordMismatchCount} "
            f"{Color.fg('royal_blue')}status: {Color.fg('daffodil')}{status} \n{Color.fg('royal_blue')}createdAt: "
            f"{Color.fg('periwinkle')}{createdAt} {Color.fg('royal_blue')}updatedAt: "
            f"{Color.fg('indigo')}{updatedAt}]{Color.reset()}"
        )

        if keys:
            logger.info(f"{Color.fg('gray')}My joined communities: {Color.fg('pink')}{' | '.join(keys)}")
    except AttributeError as e:
        if "NoneType" in str(e):
            logger.error(f"Check API response maybe is 401? - 'Nonetype'")
    except Exception as e:
        logger.error(f"An unexpected error occurred during API requests: {e}")
        
async def retry():
        retry_count = 0
        max_retries = 6
        while retry_count < max_retries:
            try:
                is_cookie_valid = await BerrizAPIClient().cookie()
                if is_cookie_valid != {}:
                    break
                else:
                    retry_count += 1
                    await asyncio.sleep(0.25)

            except Exception as e:
                if str(e) == 'request_berriz_api trigger token refresh failed':
                    return False
                retry_count += 2
                await asyncio.sleep(1)

        if retry_count == max_retries:
            return False