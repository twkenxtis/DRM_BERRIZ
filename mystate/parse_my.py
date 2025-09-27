import asyncio


from static.color import Color
from lib.lock_cookie import cookie_session, Lock_Cookie
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import My


logger = setup_logging('parse_my', 'ruby')


async def request_my():
    if cookie_session in ({}, None):
        await Lock_Cookie.cookie_session()

    try:
        data, locat, notif, my_data, me = await asyncio.gather(
            My().fetch_my(),
            My().fetch_location(),
            My().notifications(),
            My().fetch_me(),
            My().get_me_info()
        )
        if all([data, locat, notif, my_data, me]) is not None:
            # 提取資料並使用 .get() 方法，以避免 KeyError
            my_id = data.get('data', {}).get('memberInfo', {}).get('memberKey')
            my_email = data.get('data', {}).get('memberInfo', {}).get('memberEmail')
            
            location = locat.get('data', {}).get('countryCode')

            me_info = my_data.get('data', {})
            memberKey = me_info.get('memberKey')
            email = me_info.get('email')
            passwordRegistered = me_info.get('passwordRegistered')
            passwordMismatchCount = me_info.get('passwordMismatchCount')
            status = me_info.get('status')
            createdAt = me_info.get('createdAt')
            updatedAt = me_info.get('updatedAt')
            me_info = me.get('data', {})
            email2 = me_info.get('email')
            contactEmail = me_info.get('contactEmail')
            country = me_info.get('country')
            phoneNumber= me_info.get('phoneNumber')

            # 提取社羣金鑰
            join_community = notif.get('data', {}).get('contents', [])
            keys = [i.get("communityKey") for i in join_community if i.get("communityKey")]
            
            logger.info(
                f"{Color.fg('royal_blue')}Login to: {Color.fg('crimson')}{my_id}{Color.reset()}"
                f" {Color.fg('royal_blue')}Mail: {Color.fg('periwinkle')}{my_email}{Color.reset()}"
                f" {Color.fg('royal_blue')}➤  {Color.fg('amber')}{location}{Color.reset()}"
                f" {Color.fg('royal_blue')}\nmemberKey: {Color.fg('khaki')}{memberKey} {Color.fg('lavender')}{email} "
                f"{Color.fg('royal_blue')}passwordRegistered: {Color.fg('lemon')}{passwordRegistered} "
                f"{Color.fg('royal_blue')}passwordMismatchCount: {Color.fg('chocolate')}{passwordMismatchCount} "
                f"{Color.fg('royal_blue')}status: {Color.fg('daffodil')}{status} \n{Color.fg('royal_blue')}createdAt: "
                f"{Color.fg('periwinkle')}{createdAt} {Color.fg('royal_blue')}updatedAt: "
                f"{Color.fg('indigo')}{updatedAt}{Color.reset()}"
                f"{Color.fg('flamingo_pink')} email: {Color.fg('dark_red')}{email2} \n{Color.fg('flamingo_pink')}contactEmail:"
                f"{Color.fg('light_cyan')} {contactEmail} {Color.reset()}"
                f"{Color.fg('flamingo_pink')}country: {Color.fg('gold')}{country} "
                f"{Color.fg('flamingo_pink')}phoneNumber: {Color.fg('sunflower')} {phoneNumber} "
            )

            if keys:
                logger.info(f"{Color.fg('gray')}My joined community: {Color.fg('pink')}{' | '.join(keys)}")
    except AttributeError as e:
        if "NoneType" in str(e):
            pass
    except Exception as e:
        logger.error(f"An unexpected error occurred during API requests: {e}")