import asyncio
import aiohttp
from typing import Dict, Optional
from aiohttp import ClientTimeout
import json

import aiohttp

from typing import Any, Dict, List, Optional, Tuple, Union

from cookies.cookies import Berriz_cookie
from static.color import Color
from mystate.fanclub import fanclub_main
from unit.handle_log import setup_logging
from unit.image.parse_public_contexts import parse_public_contexts
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
    async def parse(data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], Optional[str], bool]:
        if not MediaParser._is_valid_response(data):
            return [], [], None, False

        contents = MediaParser._get_contents(data)
        cursor, has_next = MediaParser._extract_pagination(data)
        
        vod_list, photo_list = MediaParser._extract_media_items(contents)
        v_fanclub_list, v_not_fanclub_list = MediaParser.fanclub_items(vod_list)
        fanclub_list, not_fanclub_list = MediaParser.fanclub_items(photo_list)
        
        if Berriz_cookie()._cookies == {}:
            vod_list = ''
            v_not_fanclub_list = ''
            
        t = await FanClubFilter.is_fanclub()
        if t is not None:
            id = await get_community(t)
            p = await MediaParser.parse_fanclub_community(contents, id)
            v_list, p_list = MediaParser._extract_media_items(p)
            if paramstore.get('fanclub') is None:
                return vod_list + v_list, photo_list + p_list, cursor, has_next
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
    def _extract_media_items(contents: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        vod_list, photo_list = [], []
        for item in contents:
            media = item.get("media")
            if not media:
                raise
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
        
    async def get_all_media_lists(self) -> Tuple[List[Dict], List[Dict]]:
        vod_total, photo_total = [], []
        self.community_id = await self.get_community_id(self.community_id)
        params = await self._build_params(cursor=None)
        while True:
            data = await MediaList().media_list(self.community_id, params)
            if not data:
                break

            vods, photos, cursor, has_next = await MediaParser.parse(data)
            
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
    
    async def get_community_id(self, community_id: Union[str, int]) -> Optional[int]:
        if type(community_id) == int:
            return community_id
        if type(community_id) == str:
            community_id = await get_community(community_id)
        if community_id is None:
            logger.error(f"Community ID is {Color.fg('bright_red')}None{Color.reset()}")
            logger.info(await get_community_print())
            return None
