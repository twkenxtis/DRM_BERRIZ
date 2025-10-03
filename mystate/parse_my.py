import asyncio

from typing import Any, Dict, List, Optional

from static.color import Color
from lib.lock_cookie import cookie_session, Lock_Cookie
from unit.handle.handle_log import setup_logging
from unit.http.request_berriz_api import My


logger = setup_logging('parse_my', 'ruby')


async def request_my() -> None:
    """
    異步請求多個使用者相關的 API 端點，處理 Cookie，並記錄解析後的個人資訊
    """
    if cookie_session in ({}, None):
        await Lock_Cookie.cookie_session()

    try:
        data: Dict[str, Any]
        locat: Dict[str, Any]
        notif: Dict[str, Any]
        my_data: Dict[str, Any]
        me: Dict[str, Any]
        
        data, locat, notif, my_data, me = await asyncio.gather(
            My().fetch_my(),
            My().fetch_location(),
            My().notifications(),
            My().fetch_me(),
            My().get_me_info()
        )

        # 檢查所有結果是否都成功返回 (非 None)
        if all([data, locat, notif, my_data, me]) is not None:
            # --- 處理 data (fetch_my) ---
            my_id: Optional[str] = data.get('data', {}).get('memberInfo', {}).get('memberKey')
            my_email: Optional[str] = data.get('data', {}).get('memberInfo', {}).get('memberEmail')
            
            # --- 處理 locat (fetch_location) ---
            location: Optional[str] = locat.get('data', {}).get('countryCode')

            # --- 處理 my_data (fetch_me) ---
            me_info_1: Dict[str, Any] = my_data.get('data', {})
            memberKey: Optional[str] = me_info_1.get('memberKey')
            email: Optional[str] = me_info_1.get('email')
            passwordRegistered: Optional[bool] = me_info_1.get('passwordRegistered')
            passwordMismatchCount: Optional[int] = me_info_1.get('passwordMismatchCount')
            status: Optional[str] = me_info_1.get('status')
            createdAt: Optional[str] = me_info_1.get('createdAt')
            updatedAt: Optional[str] = me_info_1.get('updatedAt')
            
            # --- 處理 me (get_me_info) ---
            me_info_2: Dict[str, Any] = me.get('data', {})
            email2: Optional[str] = me_info_2.get('email')
            contactEmail: Optional[str] = me_info_2.get('contactEmail')
            country: Optional[str] = me_info_2.get('country')
            phoneNumber: Optional[str] = me_info_2.get('phoneNumber')

            # --- 提取社羣金鑰 (notifications) ---
            join_community: List[Dict[str, Any]] = notif.get('data', {}).get('contents', [])
            keys: List[str] = [
                key for item in join_community 
                if (key := item.get("communityKey")) is not None
            ]
            
            logger.info(
                f"{Color.fg('royal_blue')}Login to: {Color.fg('crimson')}{my_id}{Color.reset()}"
                f" {Color.fg('royal_blue')}Mail: {Color.fg('periwinkle')}{my_email}{Color.reset()}"
                f" {Color.fg('royal_blue')}➤  {Color.fg('amber')}{location}{Color.reset()}"
                f" {Color.fg('royal_blue')}\nmemberKey: {Color.fg('khaki')}{memberKey} {Color.fg('lavender')}{email} "
                f"{Color.fg('royal_blue')}passwordRegistered: {Color.fg('lemon')}{passwordRegistered} "
                f"{Color.fg('royal_blue')}passwordMismatchCount: {Color.fg('chocolate')}{passwordMismatchCount} "
                f"{Color.fg('royal_blue')}status: {Color.fg('daffodil')}{status} \n{Color.fg('royal_blue')}createdAt: "
                f"{Color.fg('periwinkle')}{createdAt} {Color.fg('royal_blue')}updatedAt: "
                f"{Color.fg('indigo')}{updatedAt}{Color.reset()}"
                f"{Color.fg('flamingo_pink')} email: {Color.fg('dark_red')}{email2} \n{Color.fg('flamingo_pink')}contactEmail:"
                f"{Color.fg('light_cyan')} {contactEmail} {Color.reset()}"
                f"{Color.fg('flamingo_pink')}country: {Color.fg('gold')}{country} "
                f"{Color.fg('flamingo_pink')}phoneNumber: {Color.fg('sunflower')} {phoneNumber} {Color.reset()}"
            )

            if keys:
                logger.info(f"{Color.fg('gray')}My joined community: {Color.fg('pink')}{' | '.join(keys)}")
    except AttributeError as e:
        if "NoneType" in str(e):
            # 忽略由於 None 屬性鏈接引起的錯誤
            pass
    except Exception as e:
        logger.error(f"An unexpected error occurred during API requests: {e}")