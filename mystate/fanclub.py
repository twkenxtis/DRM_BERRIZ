from typing import Any, Dict, List, Optional

from lib.__init__ import use_proxy
from lib.lock_cookie import cookie_session, Lock_Cookie
from unit.http.request_berriz_api import My
from unit.handle.handle_log import setup_logging


logger = setup_logging('fanclub', 'orange')

class FanClub:
    async def check_cookie(self) -> Optional[str]:
        if cookie_session == {}:
            await Lock_Cookie.cookie_session()
            return None
    async def request_facnclub(self) -> Dict[str, Any]:
        data: Optional[Dict[str, Any]] = await My().fetch_fanclub(use_proxy)
        logger.debug(f"Fanclub api response: {data}")
        return data

    async def fanclub_main(self) -> Optional[str]:
        await self.check_cookie()
        data = await self.request_facnclub()
        code: Optional[str] = data.get("code")
        message: Optional[str] = data.get("message")
        fanclub_list: Optional[List[Dict[str, Any]]] = data.get("data", {}).get("fanclubs")

        if code == '0000' and fanclub_list and len(fanclub_list) > 0:
            for i in fanclub_list:
                fanclub_info: Dict[str, Any] = i.get("fanclubInfo", {})
                subscriber_info: Dict[str, Any] = i.get("subscriberInfo", {})

                productKey: Optional[str] = fanclub_info.get("productKey")
                productName: Optional[str] = fanclub_info.get("productName")
                artistName: Optional[str] = fanclub_info.get("artistName")
                generation: Optional[str] = fanclub_info.get("generation")
                cardImageFront: Optional[str] = fanclub_info.get("cardImageFront")
                cardImageBack: Optional[str] = fanclub_info.get("cardImageBack")
                badgeImage: Optional[str] = fanclub_info.get("badgeImage")
                status: Optional[str] = fanclub_info.get("status")
                startDate: Optional[str] = fanclub_info.get("startDate")
                endDate: Optional[str] = fanclub_info.get("endDate")
                verifyStartDate: Optional[str] = fanclub_info.get("verifyStartDate")
                verifyEndDate: Optional[str] = fanclub_info.get("verifyEndDate")
                isVerifiable: Optional[bool] = fanclub_info.get("isVerifiable")

                subscriptionStartDate: Optional[str] = subscriber_info.get("subscriptionStartDate")
                subscriptionEndDate: Optional[str] = subscriber_info.get("subscriptionEndDate")
                purchaseDate: Optional[str] = subscriber_info.get("purchaseDate")
                fanclubUserCode: Optional[str] = subscriber_info.get("fanclubUserCode")
                status: Optional[str] = subscriber_info.get("status")

                return artistName

        return 'NOFANCLUBINFO'
