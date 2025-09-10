from cookies.cookies import Berriz_cookie
from unit.http.request_berriz_api import My


async def fanclub_main():
    if Berriz_cookie()._cookies == {}:
        return
    data = await (My().fetch_fanclub())
    if data is None:
        return
    code = data.get("code")
    messgae = data.get("message")
    fanclub = data.get("data").get("fanclubs")
    if code == '0000' and len(fanclub) > 0:
        fanclubs = data.get("data").get("fanclubs")
        for i in fanclubs:
            fanclub_info = i.get("fanclubInfo")
            subscriberInfo = i.get("subscriberInfo")
            productKey = fanclub_info.get("productKey")
            productName = fanclub_info.get("productName")
            artistName = fanclub_info.get("artistName")
            generation = fanclub_info.get("generation")
            cardImageFront = fanclub_info.get("cardImageFront")
            cardImageBack = fanclub_info.get("cardImageBack")
            badgeImage = fanclub_info.get("badgeImage")
            status = fanclub_info.get("status")
            startDate = fanclub_info.get("startDate")
            endDate = fanclub_info.get("endDate")
            verifyStartDate = fanclub_info.get("verifyStartDate")
            verifyEndDate = fanclub_info.get("verifyEndDate")
            isVerifiable = fanclub_info.get("isVerifiable")
            
            subscriptionStartDate = subscriberInfo.get("subscriptionStartDate")
            subscriptionEndDate = subscriberInfo.get("subscriptionEndDate")
            purchaseDate = subscriberInfo.get("purchaseDate")
            fanclubUserCode = subscriberInfo.get("fanclubUserCode")
            status = subscriberInfo.get("status")
            return artistName
    return None