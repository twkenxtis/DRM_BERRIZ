import asyncio
from typing import Dict, Optional
from functools import cache

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from cookies.cookies import Berriz_cookie
from static.color import Color
from mystate.fanclub import fanclub_main
from unit.handle_log import setup_logging
from unit.parameter import paramstore
from unit.community import get_community, get_community_print
from unit.http.request_berriz_api import MediaList
import random

MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]


logger = setup_logging('GetMediaList', 'turquoise')


class FanClubFilter:
    async def is_fanclub():
        context = await fanclub_main()
        """None - not fanclub"""
        return context


class MediaParser:
    @staticmethod
    async def parse(data: Dict[str, Any], time_a, time_b) -> Tuple[List[Dict], List[Dict], Optional[str], bool]:
        if not MediaParser._is_valid_response(data):
            return [], [], None, False

        contents = MediaParser._get_contents(data)
        cursor, has_next = MediaParser._extract_pagination(data)
        
        vod_list, photo_list = MediaParser._extract_media_items(contents, time_a, time_b)
        v_fanclub_list, v_not_fanclub_list = MediaParser.fanclub_items(vod_list)
        fanclub_list, not_fanclub_list = MediaParser.fanclub_items(photo_list)
        
        if Berriz_cookie()._cookies == {}:
            vod_list = ''
            v_not_fanclub_list = ''
            
        t = await FanClubFilter.is_fanclub()
        if t is not None:
            id = await get_community(t)
            p = await MediaParser.parse_fanclub_community(contents, id)
            v_list, p_list = MediaParser._extract_media_items(p, time_a, time_b)
            if paramstore.get('fanclub') is None:
                return vod_list, photo_list, cursor, has_next
            elif paramstore.get('fanclub') is False:
                return v_not_fanclub_list, not_fanclub_list, cursor, has_next
            return v_list, p_list, cursor, has_next
        else:
            return v_not_fanclub_list, not_fanclub_list, cursor, has_next

    async def parse_fanclub_community(contents: list[dict], target_id: int) -> list[dict]:
        return [
            item for item in contents
            if item.get("media", {}).get("communityId") == target_id
            and item["media"].get("isFanclubOnly") is True
        ]

    @staticmethod
    def _is_valid_response(data: Dict[str, Any]) -> bool:
        code = data.get("code")
        if code != "0000":
            logger.warning(f"API error: {code}")
            return False
        return True

    @staticmethod
    def _get_contents(data: Dict[str, Any]) -> List[Dict]:
        return data.get("data", {}).get("contents", [])

    @staticmethod
    def _extract_media_items(
        contents: List[Dict[str, Any]],
        time_a: Optional[datetime] = None,
        time_b: Optional[datetime] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        vod_list, photo_list = [], []
        
        # 檢查是否需要進行時間篩選 -> bool
        should_filter_by_time = (isinstance(time_a, datetime) and isinstance(time_b, datetime))

        # 確保時間範圍順序正確
        if should_filter_by_time and time_a > time_b:
            time_a, time_b = time_b, time_a

        for item in contents:
            media = item.get("media")
            
            if not media:
                raise ValueError("The 'media' field is missing in the media item")
            
            published_at_str = media.get("publishedAt")
            
            # 進行時間範圍篩選
            if should_filter_by_time and published_at_str:
                try:
                    # 將字串轉換為 datetime 物件，並處理時區
                    published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                    if not (time_a <= published_at <= time_b):
                        continue
                except (ValueError, TypeError):
                    continue

            match media.get("mediaType"):
                case "VOD":
                    vod_list.append(media)
                case "PHOTO":
                    photo_list.append(media)

        return vod_list, photo_list
    
    @staticmethod
    def fanclub_items(contents: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        fanclub, not_fanclub = [], []
        for item in contents:
            match item.get("isFanclubOnly"):
                case True:
                    fanclub.append(item)
                case False:
                    not_fanclub.append(item)
                case _:
                    not_fanclub.append(item)
        return fanclub, not_fanclub

    @staticmethod
    def _extract_pagination(data: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        pagination = data.get("data", {})
        cursor = pagination.get("cursor", {}).get("next")
        has_next = pagination.get("hasNext", False)
        return cursor, has_next


class MediaFetcher:
    def __init__(self, community_id: int):
        self.community_id = community_id
        
    async def get_all_media_lists(self, time_a, time_b) -> Tuple[List[Dict], List[Dict]]:
        vod_total, photo_total = [], []
        self.community_id = await asyncio.create_task(self.get_community_id(self.community_id))
        params = await asyncio.create_task(self._build_params(cursor=None))
        while True:
            data = await asyncio.create_task(MediaList().media_list(self.community_id, params))
            if not data:
                break
            vods, photos, cursor, has_next = await asyncio.create_task(MediaParser.parse(data, time_a, time_b))
            
            vod_total.extend(vods)
            photo_total.extend(photos)

            if not has_next:
                break
        return vod_total, photo_total
    
    async def _build_params(self, cursor: Optional[str]) -> Dict[str, Any]:
        pagesize = random.randint(25000, 30000)
        params = {"pageSize": pagesize, "languageCode": "en"}
        if cursor:
            params["next"] = cursor
        return params
    
    @cache
    async def get_community_id(self, community_id: Union[str, int]) -> Optional[int]:
        if type(community_id) == int:
            return community_id
        if type(community_id) == str:
            community_id = await get_community(community_id)
        if community_id is None:
            logger.error(f"Community ID is {Color.fg('bright_red')}None{Color.reset()}")
            logger.info(await get_community_print())
            return None
