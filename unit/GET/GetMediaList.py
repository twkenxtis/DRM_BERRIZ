import asyncio
import random
from datetime import datetime
from functools import cache
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.lock_cookie import cookie_session
from mystate.fanclub import fanclub_main
from static.color import Color
from unit.community import get_community, get_community_print
from unit.handle.handle_log import setup_logging
from unit.http.request_berriz_api import Live, MediaList
from static.parameter import paramstore

MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]

logger = setup_logging('GetMediaList', 'turquoise')


class FanClubFilter:
    async def is_fanclub() -> Optional[Any]:
        if paramstore.get('no_cookie') is not True:
            context: Optional[Any] = await fanclub_main()
            """None - not fanclub"""
            return context
        else:
            return None


class MediaParser:
    @staticmethod
    async def parse(
        data: Dict[str, Any], time_a: Optional[datetime], time_b: Optional[datetime]
    ) -> Tuple[List[Dict], List[Dict], List[Dict], Optional[str], bool]:
        pref: Optional[bool] = paramstore.get("fanclub")
        # Chunk 1: extract core
        contents, cursor, has_next = await MediaParser._extract_core(data)
        if contents is None:
            return [], [], [], cursor, has_next

        # Chunk 2: parse three raw lists
        vods, photos, lives = MediaParser._extract_media_items(contents, time_a, time_b)

        # Chunk 3: concurrently split fanclub vs non-fanclub
        (v_fc, v_nfc), (p_fc, p_nfc), (l_fc, l_nfc) = await asyncio.gather(
            asyncio.to_thread(MediaParser.fanclub_items, vods),
            asyncio.to_thread(MediaParser.fanclub_items, photos),
            asyncio.to_thread(MediaParser.fanclub_items, lives),
        )

        # Cookie 檢查：沒 cookie 則清空付費列表
        if cookie_session == {}:
            v_fc = p_fc = l_fc = []

        # Fanclub 身份檢查
        t: Optional[Any] = await FanClubFilter.is_fanclub()
        if t is None and pref is None:
            # 非會員 → 回傳非付費
            return v_nfc, p_nfc, l_nfc, cursor, has_next
        elif pref is True:
            # --fanclub-only
            return v_fc, p_fc, l_fc, cursor, has_next
        elif pref is False:
            return v_nfc, p_nfc, l_nfc, cursor, has_next

        # 會員 fanclub only content
        cid: int = await get_community(t)
        p_contents: List[Dict] = await MediaParser.parse_fanclub_community(contents, cid)
        v2, p2, l2 = MediaParser._extract_media_items(p_contents, time_a, time_b)
        return v2, p2, l2, cursor, has_next

    @staticmethod
    async def _extract_core(
        data: Dict[str, Any]
    ) -> Tuple[Optional[List[Dict]], Optional[str], bool]:
        if not MediaParser._is_valid_response(data):
            return None, None, False
        contents, (cursor, has_next) = await asyncio.gather(
            MediaParser._get_contents(data),
            MediaParser._extract_pagination(data)
        )
        return contents, cursor, has_next

    async def parse_fanclub_community(contents: List[Dict], target_id: int) -> List[Dict]:
        return [
            item for item in contents
            if item.get("media", {}).get("communityId") == target_id
            and item["media"].get("isFanclubOnly") is True
        ]

    @staticmethod
    def _is_valid_response(data: Dict[str, Any]) -> bool:
        if data is None:
            return False
        code: Optional[str] = data.get("code")
        if code != "0000":
            logger.warning(f"API error: {code}")
            return False
        return True

    @staticmethod
    async def _get_contents(data: Dict[str, Any]) -> List[Dict]:
        return data.get("data", {}).get("contents", [])

    @staticmethod
    def _extract_media_items(
        contents: List[Dict[str, Any]],
        time_a: Optional[datetime] = None,
        time_b: Optional[datetime] = None
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        vod_list: List[Dict] = []
        photo_list: List[Dict] = []
        live_list: List[Dict] = []
        
        # 檢查是否需要進行時間篩選 -> bool
        should_filter_by_time: bool = (isinstance(time_a, datetime) and isinstance(time_b, datetime))

        for item in contents:
            media: Optional[Dict[str, Any]] = item.get("media")
            
            if not media:
                raise ValueError("The 'media' field is missing in the media item")
            
            published_at_str: Optional[str] = media.get("publishedAt")
            # 進行時間範圍篩選
            if should_filter_by_time and published_at_str:
                try:
                    # 將字串轉換為 datetime 物件，並處理時區
                    published_at: datetime = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                    if not (time_a <= published_at <= time_b):
                        continue
                except (ValueError, TypeError):
                    continue
            match media.get("mediaType"):
                case "VOD":
                    vod_list.append(media)
                case "PHOTO":
                    photo_list.append(media)
                case "LIVE":
                    live_list.append(media)
        return vod_list, photo_list, live_list
    
    @staticmethod
    def fanclub_items(contents: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        fanclub: List[Dict] = []
        not_fanclub: List[Dict] = []
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
    async def _extract_pagination(data: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        pagination: Dict[str, Any] = data.get("data", {})
        cursor: Optional[str] = pagination.get("cursor", {}).get("next")
        has_next: bool = pagination.get("hasNext", False)
        return cursor, has_next


class MediaFetcher:
    def __init__(self, community_id: int | str):
        self.community_id: int | str = community_id

    async def get_all_media_lists(self, time_a: Optional[datetime], time_b: Optional[datetime]) -> Tuple[List[Dict], List[Dict], List[Dict]] | bool:
        vod_total: List[Dict] = []
        photo_total: List[Dict] = []
        live_total: List[Dict] = []
        await self.handle_community_input()
        params: Dict[str, Any] = await self._build_params(cursor=None)

        while True:
            if self.community_id is None:
                logger.error(f"{Color.fg('ruby')}Community ID is None{Color.reset()}")
                return False

            # 並行拉 raw data
            media_data, live_data = await asyncio.gather(
                MediaList().media_list(self.community_id, params),
                Live().fetch_live_replay(self.community_id, params),
            )
            if not (media_data or live_data):
                if not media_data and live_data:
                    M = 'Media data'
                elif not live_data and media_data:
                    M = 'Live data'
                else:
                    M = 'Media and Live data'
                    logger.warning(
                        f"Fail to get 【{Color.fg('light_yellow')}{M}"
                        f"{Color.fg('gold')}】"
                    )
                break

            # 並行解析 + build params
            (vods, photos, params_media, has_next_media), \
            (lives, params_live, has_next_live) = await asyncio.gather(
                self._process_media_chunk(media_data, time_a, time_b),
                self._process_live_chunk(live_data,   time_a, time_b),
            )

            vod_total  .extend(vods)
            photo_total.extend(photos)
            live_total .extend(lives)

            if not (has_next_media or has_next_live):
                break

            # 合併下一輪要用的 params
            params = {
                "media": params_media,
                "live":  params_live,
            }

        return vod_total, photo_total, live_total

    async def handle_community_input(self) -> Optional[int | str]:
        if type(self.community_id) == int:
            return self.community_id
        elif type(self.community_id) == str:
            self.community_id = await get_community(self.community_id)
            await self.get_community_id(self.community_id)
            return self.community_id
        return None

    async def _init_state(self) -> Tuple[str, Dict[str, Any]]:
        cid: str = await self.get_community_id(self.community_id)
        params: Dict[str, Any] = await self._build_params(cursor=None)
        return cid, params

    async def _fetch_data(
        self, community_id: str, params: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return await asyncio.gather(
            MediaList().media_list(community_id, params),
            Live().fetch_live_replay(community_id, params),
        )

    async def _process_media_chunk(
        self, media_data: Dict[str, Any], time_a: Optional[datetime], time_b: Optional[datetime]
    ) -> Tuple[List[Dict], List[Dict], Dict[str, Any], bool]:
        vods, photos, _, cursor, has_next = await MediaParser.parse(
            media_data, time_a, time_b
        )
        next_params: Dict[str, Any] = await self._build_params(cursor)
        return vods, photos, next_params, has_next

    async def _process_live_chunk(
        self, live_data: Dict[str, Any], time_a: Optional[datetime], time_b: Optional[datetime]
    ) -> Tuple[List[Dict], Dict[str, Any], bool]:
        _, _, lives, cursor, has_next = await MediaParser.parse(
            live_data, time_a, time_b
        )
        next_params: Dict[str, Any] = await self._build_params(cursor)
        return lives, next_params, has_next
    
    async def _build_params(self, cursor: Optional[str]) -> Dict[str, Any]:
        pagesize: int = random.randint(25000, 30000)
        params: Dict[str, Any] = {"pageSize": pagesize, "languageCode": "en"}
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
        return community_id